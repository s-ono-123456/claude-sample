# Stage 1: Build
FROM maven:3.9-eclipse-temurin-11 AS build

WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -DskipTests -q

# Stage 2: Run
FROM tomcat:9.0-jre11

RUN rm -rf ${CATALINA_HOME}/webapps/ROOT
COPY --from=build /app/target/sample-app-1.0-SNAPSHOT.war ${CATALINA_HOME}/webapps/ROOT.war

EXPOSE 8080
CMD ["catalina.sh", "run"]
