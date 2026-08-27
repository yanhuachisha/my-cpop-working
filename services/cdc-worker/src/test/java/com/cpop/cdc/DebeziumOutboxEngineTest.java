package com.cpop.cdc;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class DebeziumOutboxEngineTest {
    @Test
    void aggregateRoutingIsStableAndBounded() {
        String aggregateId = "memory-42";
        int first = DebeziumOutboxEngine.bucketFor(aggregateId);
        assertThat(first).isBetween(0, 7);
        assertThat(DebeziumOutboxEngine.bucketFor(aggregateId)).isEqualTo(first);
    }
}
