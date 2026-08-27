package com.cpop.projector;

import java.util.ArrayList;
import java.util.List;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarable;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitProjectionConfiguration {
    static final String EXCHANGE = "agent.memory.events";
    static final String DLX = "agent.memory.dlx";

    @Bean
    Declarables memoryTopology() {
        List<Declarable> items = new ArrayList<>();
        DirectExchange exchange = new DirectExchange(EXCHANGE, true, false);
        DirectExchange dlx = new DirectExchange(DLX, true, false);
        items.add(exchange);
        items.add(dlx);
        for (int bucket = 0; bucket < 8; bucket++) {
            String name = "agent.memory.project." + bucket;
            Queue queue = QueueBuilder.durable(name).deadLetterExchange(DLX).deadLetterRoutingKey("memory.dlq").build();
            items.add(queue);
            items.add(BindingBuilder.bind(queue).to(exchange).with("memory." + bucket));
        }
        Queue dlq = QueueBuilder.durable("agent.memory.project.dlq").build();
        items.add(dlq);
        items.add(BindingBuilder.bind(dlq).to(dlx).with("memory.dlq"));
        return new Declarables(items);
    }

    @Bean
    SimpleRabbitListenerContainerFactory manualAckContainerFactory(ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setConcurrentConsumers(1);
        factory.setMaxConcurrentConsumers(1);
        factory.setPrefetchCount(10);
        return factory;
    }
}
