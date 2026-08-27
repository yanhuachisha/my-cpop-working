package com.cpop.projector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.web.reactive.function.client.WebClient;

class MemoryProjectorTest {
    @Test
    void staleOrDuplicateVersionIsAckedAndUsesStrictExternalVersioning() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicReference<String> esQuery = new AtomicReference<>();
        server.createContext("/v1/embeddings", exchange -> respond(
                exchange,
                200,
                "{\"data\":[{\"embedding\":["
                        + String.join(",", Collections.nCopies(1024, "0.0"))
                        + "]}]}"));
        server.createContext("/agent_memory_current", exchange -> {
            esQuery.set(exchange.getRequestURI().getQuery());
            respond(exchange, 409, "{\"error\":\"version_conflict_engine_exception\"}");
        });
        server.start();
        try {
            String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            MemoryProjector projector = new MemoryProjector(
                    new ObjectMapper(), WebClient.builder(), baseUrl, baseUrl);
            MessageProperties properties = new MessageProperties();
            properties.setDeliveryTag(7L);
            String event = """
                    {"aggregate_id":"memory-1","aggregate_version":2,"payload":{
                      "tenant_id":"tenant-1","user_id":"user-1","memory_key":"key-1",
                      "memory_type":"preference","subject":"user","predicate":"prefers",
                      "content":"jazz","authority":1.0}}
                    """;
            Channel channel = mock(Channel.class);

            projector.project(
                    new Message(event.getBytes(StandardCharsets.UTF_8), properties), channel);

            assertThat(esQuery.get()).contains("version=2", "version_type=external");
            verify(channel).basicAck(7L, false);
        } finally {
            server.stop(0);
        }
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }
}
