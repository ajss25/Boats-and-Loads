# Boats and Loads

A REST API that uses proper resource based URLs, pagination, status codes, and system for creating users and authorization. Deployed on the Google Cloud Platform.

### Overview

- A User entity and two other non-user entities (Boats and Loads).
- Boats and Loads are related to each other, and the Users are related to the Boats.
- Resources corresponding to the Users are protected.
- Each entity has a collection URL provided.
- Every entity supports all 4 CRUD operations, and handles side effects.

### About

- Developed with Python and Flask, and deployed with the Google App Engine and Google Datastore.
- Please read the API SPEC document for a complete overview of the project
