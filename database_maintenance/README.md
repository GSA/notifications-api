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

cf run-task notify-cycle-history "flask command cycle-notification-history-table -l 100000 -s '2020-03-18 00:00' -e '2020-03-19 00:00"
  



- Deploy new command - cycle_notification_history_table to prod
- script_1.sql
    - create nh_pivot
    - create nh trigger
    - create new index on nh
- foreign_keys.sql
- run command for each day in nh --> start October 1, 2019
-- all data in NH
- 




