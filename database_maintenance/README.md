Create a new app to test command

DO NOT commit new manifest file

Add to MakeFile
'notify-cycle-history': {
    'NOTIFY_APP_NAME': 'api',
    'instances': {
      'preview': 0,
      'staging': 0,
      'production': 0
    },
  },

CF_APP=notify-cycle-history CF_SPACE=staging make generate-manifest > cycle-history-manifest.yml
cf v3-create-app notify-cycle-history 
cf v3-apply-manifest -f cycle-history-manifest.yml
cf v3-push notify-cycle-history