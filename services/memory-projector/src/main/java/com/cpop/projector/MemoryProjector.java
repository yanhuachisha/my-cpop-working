package com.cpop.projector;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.util.Map;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class MemoryProjector {
    private final ObjectMapper mapper;
    private final WebClient modelClient;
    private final WebClient esClient;

    public MemoryProjector(ObjectMapper mapper, WebClient.Builder builder,
            @Value("${model-service.url:http://localhost:8010}") String modelUrl,
            @Value("${elasticsearch.url:http://localhost:9200}") String elasticsearchUrl) {
        this.mapper = mapper;
        this.modelClient = builder.baseUrl(modelUrl).build();
        this.esClient = builder.baseUrl(elasticsearchUrl).build();
    }

    @RabbitListener(
            queues = {"agent.memory.project.0", "agent.memory.project.1", "agent.memory.project.2",
                    "agent.memory.project.3", "agent.memory.project.4", "agent.memory.project.5",
                    "agent.memory.project.6", "agent.memory.project.7"},
            containerFactory = "manualAckContainerFactory")
    public void project(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();
        try {
            JsonNode event = mapper.readTree(message.getBody());
            JsonNode payload = event.path("payload");
            long version = event.path("aggregate_version").asLong();
            String memoryId = event.path("aggregate_id").asText();
            JsonNode embeddingResponse = modelClient.post().uri("/v1/embeddings")
                    .bodyValue(Map.of("texts", new String[]{payload.path("content").asText()}))
                    .retrieve().bodyToMono(JsonNode.class).block();
            if (embeddingResponse == null) throw new IllegalStateException("embedding response is empty");
            JsonNode embedding = embeddingResponse.path("data").path(0).path("embedding");
            var document = mapper.createObjectNode()
                    .put("memory_id", memoryId)
                    .put("tenant_id", payload.path("tenant_id").asText())
                    .put("user_id", payload.path("user_id").asText())
                    .put("memory_key", payload.path("memory_key").asText())
                    .put("memory_type", payload.path("memory_type").asText())
                    .put("title", payload.path("subject").asText() + " " + payload.path("predicate").asText())
                    .put("content", payload.path("content").asText())
                    .put("authority", payload.path("authority").asDouble(1.0))
                    .put("aggregate_version", version)
                    .set("embedding", embedding);
            esClient.put().uri(uri -> uri.path("/agent_memory_current/_doc/{id}")
                            .queryParam("version", version).queryParam("version_type", "external").build(memoryId))
                    .bodyValue(document).retrieve()
                    .onStatus(status -> status.value() == 409, response -> response.bodyToMono(String.class)
                            .thenReturn(new StaleProjectionException()))
                    .toBodilessEntity().block();
            channel.basicAck(tag, false);
        } catch (StaleProjectionException stale) {
            channel.basicAck(tag, false);
        } catch (Exception error) {
            channel.basicNack(tag, false, false);
        }
    }

    private static final class StaleProjectionException extends RuntimeException {}
}
