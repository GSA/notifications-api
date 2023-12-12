# notify.gov Data Dictionary

This document serves as a comprehensive guide to the data structure of notify.gov. It outlines the key data elements, their types, and relationships within the system. From user information to message details, this data dictionary is a valuable resource for understanding and maintaining the underlying data model of this application. Use this guide to ensure consistency, clarity, and effective management of the data that powers our messaging functionality.

## Table: Dashboard

| Field        | Type      | Length | Description                        |
|--------------|-----------|--------|------------------------------------|
| ProductID    | Integer   |        | Unique identifier for a product.   |
| Name         | Varchar   | 100    | Name of the product.               |
| Price        | Decimal   |        | Price of the product.              |
| CategoryID   | Integer   |        | Foreign key to product category.   |
