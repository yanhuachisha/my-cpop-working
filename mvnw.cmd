@echo off
setlocal
set "JAVA_HOME=C:\Users\super\Desktop\jdk-17.0.12"
if not "%CPOP_JAVA_HOME%"=="" set "JAVA_HOME=%CPOP_JAVA_HOME%"
if not exist "%JAVA_HOME%\bin\java.exe" (
  echo JDK 17 not found at "%JAVA_HOME%" 1>&2
  exit /b 1
)
set "MAVEN_VERSION=3.9.9"
set "MAVEN_HOME=%~dp0.mvn\apache-maven-%MAVEN_VERSION%"
if not exist "%MAVEN_HOME%\bin\mvn.cmd" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$zip='%TEMP%\apache-maven-%MAVEN_VERSION%-bin.zip'; Invoke-WebRequest 'https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/%MAVEN_VERSION%/apache-maven-%MAVEN_VERSION%-bin.zip' -OutFile $zip; Expand-Archive -Force $zip '%~dp0.mvn'"
  if errorlevel 1 exit /b 1
)
call "%MAVEN_HOME%\bin\mvn.cmd" -f "%~dp0services\pom.xml" %*
exit /b %errorlevel%
