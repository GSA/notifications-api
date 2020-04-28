--- Just a holding place to create a table to cycle the Notification history table
create table temp_notification_history (
  id                      | uuid                        | not null
job_id                  | uuid                        |
job_row_number          | integer                     |
service_id              | uuid                        |
template_id             | uuid                        |
template_version        | integer                     | not null
api_key_id              | uuid                        |
key_type                | character varying           | not null
notification_type       | notification_type           | not null
created_at              | timestamp without time zone | not null
sent_at                 | timestamp without time zone |
sent_by                 | character varying           |
updated_at              | timestamp without time zone |
reference               | character varying           |
billable_units          | integer                     | not null
client_reference        | character varying           |
international           | boolean                     |
phone_prefix            | character varying           |
rate_multiplier         | numeric                     |
notification_status     | text                        |
created_by_id           | uuid                        |
postage                 | character varying           |
document_download_count | integer                     |

)
with indexes