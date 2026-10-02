targetScope = 'resourceGroup'

@description('Region for the new VM and networking.')
param location string = resourceGroup().location

@description('Your public IPv4 address followed by /32. Never use * or 0.0.0.0/0.')
param allowedCidr string

@description('Published, reviewed Git commit containing the Dockerfile; exactly 40 hex characters.')
@minLength(40)
@maxLength(40)
param codeCommit string

@description('Existing RBAC-enabled Key Vault in this resource group, Azure public cloud.')
param keyVaultName string

param secretName string = 'openai-api-key'

@description('Existing SSH public key for the Linux administrator. SSH network access remains closed.')
param adminSshPublicKey string

@allowed(['Standard_B2s', 'Standard_B2ms'])
param vmSize string = 'Standard_B2s'

var name = 'book-recommender'

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource secret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: vault
  name: secretName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-identity'
  location: location
}

resource secretReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(secret.id, identity.id, 'KeyVaultSecretsUser')
  scope: secret
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${name}-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowDemoFromYourIp'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: allowedCidr
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '7860'
        }
      }
      {
        name: 'DenyOtherInbound'
        properties: {
          priority: 200
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${name}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.42.0.0/16'] }
    subnets: [{ name: 'app', properties: { addressPrefix: '10.42.0.0/24' } }]
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${name}-ip'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: '${name}-nic'
  location: location
  properties: {
    networkSecurityGroup: { id: nsg.id }
    ipConfigurations: [{
      name: 'primary'
      properties: {
        privateIPAllocationMethod: 'Dynamic'
        subnet: { id: '${network.id}/subnets/app' }
        publicIPAddress: { id: publicIp.id }
      }
    }]
  }
}

var config = base64(string({
  codeCommit: codeCommit
  vaultUri: vault.properties.vaultUri
  secretName: secretName
  clientId: identity.properties.clientId
}))
var customData = replace(replace(loadTextContent('cloud-init.yaml'), '__CONFIG_BASE64__', config),
  '__BOOTSTRAP_SCRIPT__', replace(loadTextContent('azure_bootstrap.py'), '\n', '\n      '))

resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: name
      adminUsername: 'azureuser'
      customData: base64(customData)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        ssh: { publicKeys: [{ path: '/home/azureuser/.ssh/authorized_keys', keyData: adminSshPublicKey }] }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        diskSizeGB: 30
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        deleteOption: 'Delete'
      }
    }
    networkProfile: { networkInterfaces: [{ id: nic.id }] }
  }
  dependsOn: [secretReader]
}

output service string = 'Azure Virtual Machines'
output vmName string = vm.name
output appUrl string = 'http://${publicIp.properties.ipAddress}:7860'
