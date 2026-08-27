FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY services/pom.xml services/pom.xml
COPY services/cdc-worker services/cdc-worker
RUN mvn -f services/pom.xml -pl cdc-worker -am package -DskipTests
FROM eclipse-temurin:17-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /workspace/services/cdc-worker/target/cdc-worker-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
