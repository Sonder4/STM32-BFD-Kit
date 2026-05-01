#ifndef BFD_TELEMETRY_RING_H
#define BFD_TELEMETRY_RING_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BFD_TELEMETRY_RING_MAGIC 0x54444642u
#define BFD_TELEMETRY_RING_ABI_VERSION 1u

typedef struct
{
    uint32_t seq;
    uint32_t time_us;
    uint16_t payload_size;
    uint16_t flags;
} BfdTelemetryRecordHeader_t;

typedef struct
{
    uint32_t magic;
    uint16_t abi_version;
    uint16_t header_size;
    uint16_t record_stride;
    uint16_t reserved0;
    uint32_t capacity;
    volatile uint32_t write_seq;
    volatile uint32_t dropped_records;
    volatile uint32_t flags;
    uint32_t reserved1;
} BfdTelemetryRingHeader_t;

typedef struct
{
    BfdTelemetryRingHeader_t* header;
    uint8_t* storage;
} BfdTelemetryRing_t;

uint32_t BfdTelemetryRing_AlignUp(uint32_t value, uint32_t alignment);
uint16_t BfdTelemetryRing_MinRecordStride(uint16_t payload_size);
uint32_t BfdTelemetryRing_ImageSizeBytes(uint16_t record_stride, uint32_t capacity);
int BfdTelemetryRing_Init(BfdTelemetryRing_t* ring,
                          BfdTelemetryRingHeader_t* header,
                          void* storage,
                          uint16_t record_stride,
                          uint32_t capacity);
int BfdTelemetryRing_Publish(BfdTelemetryRing_t* ring,
                             uint32_t time_us,
                             uint16_t flags,
                             const void* payload,
                             uint16_t payload_size);

#ifdef __cplusplus
}
#endif

#endif
