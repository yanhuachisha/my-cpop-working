package com.cpop.cdc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import io.debezium.engine.format.Json;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DebeziumOutboxEngine {
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final String mysqlHost;
    private final int mysqlPort;
    private final String mysqlUser;
    private final String mysqlPassword;
    private final Path dataDirectory;
    private DebeziumEngine<ChangeEvent<String, String>> engine;

    public DebeziumOutboxEngine(RabbitTemplate rabbit, ObjectMapper mapper,
            @Value("${cdc.mysql.host:mysql}") String mysqlHost,
            @Value("${cdc.mysql.port:3306}") int mysqlPort,
            @Value("${cdc.mysql.user:debezium}") String mysqlUser,
            @Value("${cdc.mysql.password:debezium}") String mysqlPassword,
            @Value("${cdc.data-directory:/var/lib/cdc}") String dataDirectory) {
        this.rabbit = rabbit;
        this.mapper = mapper;
        this.mysqlHost = mysqlHost;
        this.mysqlPort = mysqlPort;
        this.mysqlUser = mysqlUser;
        this.mysqlPassword = mysqlPassword;
        this.dataDirectory = Path.of(dataDirectory);
    }

    @PostConstruct
    void start() throws IOException {
        Files.createDirectories(dataDirectory);
        engine = DebeziumEngine.create(Json.class)
                .using(properties())
                .notifying(this::publish)
                .build();
        executor.execute(engine);
    }

    @PreDestroy
    void stop() throws IOException {
        if (engine != null) engine.close();
        executor.shutdownNow();
    }

    private void publish(ChangeEvent<String, String> event) {
        try {
            JsonNode envelope = mapper.readTree(event.value());
            JsonNode after = envelope.path("payload").path("after");
            if (after.isMissingNode() || after.isNull()) return;
            String aggregateId = after.path("aggregate_id").asText();
            int bucket = bucketFor(aggregateId);
            String message = mapper.writeValueAsString(mapper.createObjectNode()
                    .put("event_id", after.path("id").asText())
                    .put("aggregate_id", aggregateId)
                    .put("aggregate_version", after.path("aggregate_version").asInt())
                    .put("event_type", after.path("event_type").asText())
                    .put("trace_id", after.path("trace_id").asText())
                    .set("payload", parsePayload(after.path("payload"))));
            rabbit.convertAndSend(RabbitConfiguration.EXCHANGE, "memory." + bucket, message);
        } catch (Exception error) {
            throw new IllegalStateException("cannot publish outbox event", error);
        }
    }

    private JsonNode parsePayload(JsonNode payload) throws IOException {
        return payload.isTextual() ? mapper.readTree(payload.asText()) : payload;
    }

    static int bucketFor(String aggregateId) {
        return Math.floorMod(aggregateId.hashCode(), 8);
    }

    private Properties properties() {
        Properties props = new Properties();
        props.setProperty("name", "cpop-outbox-cdc");
        props.setProperty("connector.class", "io.debezium.connector.mysql.MySqlConnector");
        props.setProperty("database.hostname", mysqlHost);
        props.setProperty("database.port", Integer.toString(mysqlPort));
        props.setProperty("database.user", mysqlUser);
        props.setProperty("database.password", mysqlPassword);
        props.setProperty("database.server.id", "5401");
        props.setProperty("topic.prefix", "cpop");
        props.setProperty("database.include.list", "cpop_atlas");
        props.setProperty("table.include.list", "cpop_atlas.outbox_event");
        props.setProperty("snapshot.mode", "initial");
        props.setProperty("offset.storage", "org.apache.kafka.connect.storage.FileOffsetBackingStore");
        props.setProperty("offset.storage.file.filename", dataDirectory.resolve("offsets.dat").toString());
        props.setProperty("offset.flush.interval.ms", "1000");
        props.setProperty("schema.history.internal", "io.debezium.storage.file.history.FileSchemaHistory");
        props.setProperty("schema.history.internal.file.filename", dataDirectory.resolve("schema-history.dat").toString());
        return props;
    }
}
