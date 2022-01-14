# Boats and Loads

A RESTful API using resource based URLs, pagination, status codes, and system for creating users and authorization. End users can manage data and relationships between Users, Boats, and Loads.

### Key Features

- A User entity and two other non-user entities (Boats and Loads).
- Users are related to the Boats, and Boats and Loads are related to each other.
- Resources corresponding to the Users are protected.
- Each entity has a collection URL provided.
- Each entity supports CRUD operations and handles side effects.
- A JSON Web Token (JWT) can be created by end users and be used to authorize requests to User-related entities.

### Learn More

- Developed with Python and Flask, and deployed with the Google App Engine and Google Datastore on the Google Cloud Platform.
- Explore the API SPEC document, and the Postman Test Collection for a complete overview of the project!
