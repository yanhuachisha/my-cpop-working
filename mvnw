#!/bin/sh
set -eu
JAVA_HOME="${JAVA_HOME:-/opt/java/openjdk}"
MAVEN_VERSION=3.9.9
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MAVEN_HOME="$BASE_DIR/.mvn/apache-maven-$MAVEN_VERSION"
if [ ! -x "$MAVEN_HOME/bin/mvn" ]; then
  curl -fsSL "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/$MAVEN_VERSION/apache-maven-$MAVEN_VERSION-bin.tar.gz" | tar -xz -C "$BASE_DIR/.mvn"
fi
exec "$MAVEN_HOME/bin/mvn" -f "$BASE_DIR/services/pom.xml" "$@"
