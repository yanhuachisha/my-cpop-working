package com.cpop.cdc;

import org.springframework.amqp.core.DirectExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitConfiguration {
    public static final String EXCHANGE = "agent.memory.events";

    @Bean
    DirectExchange memoryExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }
}
