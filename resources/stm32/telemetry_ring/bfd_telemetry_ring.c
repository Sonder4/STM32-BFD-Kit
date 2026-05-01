#include "bfd_telemetry_ring.h"

#include <stddef.h>
#include <string.h>

static void BfdTelemetryRing_MemoryBarrier(void)
{
#if defined(__GNUC__) || defined(__clang__)
    __sync_synchronize();
#else
    __asm volatile("" ::: "memory");
#endif
}

uint32_t BfdTelemetryRing_AlignUp(uint32_t value, uint32_t alignment)
{
    uint32_t remainder;

    if (alignment == 0u) {
        return value;
    }

    remainder = value % alignment;
    if (remainder == 0u) {
        return value;
    }
    return value + alignment - remainder;
}

uint16_t BfdTelemetryRing_MinRecordStride(uint16_t payload_size)
{
    return (uint16_t)BfdTelemetryRing_AlignUp(
        (uint32_t)sizeof(BfdTelemetryRecordHeader_t) + (uint32_t)payload_size,
        4u);
}

uint32_t BfdTelemetryRing_ImageSizeBytes(uint16_t record_stride, uint32_t capacity)
{
    return (uint32_t)sizeof(BfdTelemetryRingHeader_t) + ((uint32_t)record_stride * capacity);
}

int BfdTelemetryRing_Init(BfdTelemetryRing_t* ring,
                          BfdTelemetryRingHeader_t* header,
                          void* storage,
                          uint16_t record_stride,
                          uint32_t capacity)
{
    if ((ring == NULL) || (header == NULL) || (storage == NULL)) {
        return -1;
    }
    if ((capacity == 0u) || (record_stride < sizeof(BfdTelemetryRecordHeader_t))) {
        return -2;
    }

    memset(header, 0, sizeof(*header));
    memset(storage, 0, (size_t)record_stride * (size_t)capacity);

    header->magic = BFD_TELEMETRY_RING_MAGIC;
    header->abi_version = BFD_TELEMETRY_RING_ABI_VERSION;
    header->header_size = (uint16_t)sizeof(BfdTelemetryRingHeader_t);
    header->record_stride = record_stride;
    header->capacity = capacity;

    ring->header = header;
    ring->storage = (uint8_t*)storage;
    return 0;
}

int BfdTelemetryRing_Publish(BfdTelemetryRing_t* ring,
                             uint32_t time_us,
                             uint16_t flags,
                             const void* payload,
                             uint16_t payload_size)
{
    uint32_t write_seq;
    uint32_t slot_index;
    uint8_t* slot;
    BfdTelemetryRecordHeader_t* record_header;
    uint16_t max_payload_size;

    if ((ring == NULL) || (ring->header == NULL) || (ring->storage == NULL)) {
        return -1;
    }

    max_payload_size = (uint16_t)(ring->header->record_stride - sizeof(BfdTelemetryRecordHeader_t));
    if (payload_size > max_payload_size) {
        return -2;
    }
    if ((payload_size > 0u) && (payload == NULL)) {
        return -3;
    }

    write_seq = ring->header->write_seq;
    slot_index = write_seq % ring->header->capacity;
    slot = ring->storage + ((size_t)slot_index * (size_t)ring->header->record_stride);
    memset(slot, 0, ring->header->record_stride);

    if (payload_size > 0u) {
        memcpy(slot + sizeof(BfdTelemetryRecordHeader_t), payload, payload_size);
    }

    BfdTelemetryRing_MemoryBarrier();

    record_header = (BfdTelemetryRecordHeader_t*)slot;
    record_header->seq = write_seq;
    record_header->time_us = time_us;
    record_header->payload_size = payload_size;
    record_header->flags = flags;

    BfdTelemetryRing_MemoryBarrier();

    if (write_seq >= ring->header->capacity) {
        ring->header->dropped_records++;
    }
    ring->header->write_seq = write_seq + 1u;
    return 0;
}
