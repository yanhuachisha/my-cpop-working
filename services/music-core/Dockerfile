FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY services/pom.xml services/pom.xml
COPY services/music-core services/music-core
RUN mvn -f services/pom.xml -pl music-core -am package -DskipTests

FROM eclipse-temurin:17-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /workspace/services/music-core/target/music-core-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
