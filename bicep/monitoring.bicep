targetScope = 'resourceGroup'

@description('Action group owned only by Bicep, not Terraform.')
param actionGroupName string = 'airp-operations'

@description('Operator notification destination. Do not commit personal addresses.')
param notificationEmail string

@description('Existing AKS resource ID provisioned by Terraform.')
param clusterResourceId string

resource operations 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: 'global'
  properties: {
    groupShortName: 'airp-ops'
    enabled: true
    emailReceivers: [
      {
        name: 'operations'
        emailAddress: notificationEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource healthAlert 'Microsoft.Insights/activityLogAlerts@2020-10-01' = {
  name: 'airp-cluster-resource-health'
  location: 'global'
  properties: {
    enabled: true
    scopes: [clusterResourceId]
    condition: {
      allOf: [
        { field: 'category', equals: 'ResourceHealth' }
        { field: 'properties.currentHealthStatus', equals: 'Unavailable' }
      ]
    }
    actions: {
      actionGroups: [{ actionGroupId: operations.id }]
    }
  }
}

output actionGroupId string = operations.id