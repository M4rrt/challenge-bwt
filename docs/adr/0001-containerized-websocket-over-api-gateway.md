# Containerized WebSocket instead of AWS API Gateway WebSocket

**Status:** accepted

Real-time message delivery over WebSocket is a mandatory requirement. The README also lists native AWS API Gateway WebSocket as an extra-credit differential, as an alternative to Socket.IO/plain WebSocket. We chose to terminate WebSocket connections inside the backend container (ECS/Fargate running FastAPI's native `websockets` support) rather than through API Gateway, to avoid externalizing connection state (API Gateway + Lambda requires tracking connection IDs in DynamoDB, since Lambda is stateless between invocations) given the challenge's 8-16h time budget. This satisfies the mandatory real-time requirement but forgoes that specific extra-credit point.

With more time, migrating the WebSocket layer to API Gateway + Lambda would be the natural next step to pick up that differential.
