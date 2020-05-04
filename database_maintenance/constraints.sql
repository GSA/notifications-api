
ALTER TABLE notification_history_pivot ADD CONSTRAINT fk_notification_history_notification_status FOREIGN KEY (notification_status) REFERENCES notification_status_types(name)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_job_id_fkey FOREIGN KEY (job_id) REFERENCES jobs(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_key_type_fkey FOREIGN KEY (key_type) REFERENCES key_types(name)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_service_id_fkey FOREIGN KEY (service_id) REFERENCES services(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_templates_history_fkey FOREIGN KEY (template_id, template_version) REFERENCES templates_history(id, version)

--- Create indexes after drop table since the names need to be unique
--- Or rename these indexes (index names have to be unique in db)
CREATE INDEX CONCURRENTLY ix_notification_history_job_id ON notification_history_pivot (job_id);
CREATE INDEX CONCURRENTLY ix_notification_history_reference ON notification_history_pivot (reference);
CREATE INDEX CONCURRENTLY ix_notification_history_template_id ON notification_history_pivot (template_id);
CREATE INDEX CONCURRENTLY ix_notifications_service_id_composite ON notification_history_pivot (service_id, key_type, notification_type, created_at);

-- we could possibly not create this check constraint in the new table since we want to drop it in an outstanding PR.
--ALTER TABLE notification_history_pivot ADD CONSTRAINT chk_notification_history_postage_null CHECK (
--CASE
--    WHEN notification_type = 'letter'::notification_type
--    THEN postage IS NOT NULL AND (postage::text = ANY (ARRAY['first'::character varying, 'second'::character varying]::text[]))
--    ELSE postage IS NULL
--END)

-- Not creating these ones since we want to drop them any way.
--DROP INDEX CONCURRENTLY ix_notification_history_api_key_id;
--DROP INDEX CONCURRENTLY ix_notification_history_created_at;
--DROP INDEX CONCURRENTLY ix_notification_history_notification_status;
--DROP INDEX CONCURRENTLY ix_notification_history_notification_type;
--DROP INDEX CONCURRENTLY ix_notification_history_service_id;
--DROP INDEX CONCURRENTLY ix_notification_history_service_id_created_at;
