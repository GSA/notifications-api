# notify.gov Data Dictionary

This document serves as a comprehensive guide to the data structure of notify.gov. It outlines the key data elements, their types, and relationships within the system. From user information to message details, this data dictionary is a valuable resource for understanding and maintaining the underlying data model of this application. Use this guide to ensure consistency, clarity, and effective management of the data that powers our messaging functionality.

# Table: Global

| Field                               | Type      | Length | Description                                                      |
|-------------------------------------|-----------|--------|------------------------------------------------------------------|
| service_id                          | Integer   |        | Service ID - reference for most data related to a service        |


## Table: Dashboard

| Field                               | Type      | Length | Description                                |
|-------------------------------------|-----------|--------|--------------------------------------------|
| global_message_limit                | Integer   |        | Message limit set by platform admin        |
| daily_global_messages_remaining     | Integer   |        | Remaining messages in database             |
