#include "icon_cache.h"
#include <Arduino.h>
#include "mbedtls/base64.h"

#define ICON_SLOTS       48       // ≈ 96 Ko de PSRAM
#define ICON_REQ_RETRY_MS 2000

struct IconSlot {
    uint32_t     hash;        // 0 = libre
    uint8_t      mask;        // bit i = morceau i reçu
    bool         ready;
    uint32_t     last_use;    // LRU
    uint32_t     last_req;    // dernière demande « ?I: » (0 = jamais)
    uint8_t     *data;
    lv_img_dsc_t dsc;
};

static IconSlot slots[ICON_SLOTS];
static bool     cache_ok = false;

static uint32_t fnv1a32(const uint8_t *p, size_t len) {
    uint32_t h = 0x811C9DC5u;
    while (len--) { h ^= *p++; h *= 0x01000193u; }
    return h ? h : 1;   // 0 est réservé à « pas d'icône » (même règle côté Python)
}

void icon_cache_init(void) {
    uint8_t *pool = (uint8_t *)ps_malloc(ICON_SLOTS * ICON_BYTES);
    if (!pool) return;   // sans PSRAM : pas d'icônes, pastilles uniquement
    for (int i = 0; i < ICON_SLOTS; i++) {
        IconSlot &s = slots[i];
        memset(&s, 0, sizeof(s));
        s.data = pool + i * ICON_BYTES;
        s.dsc.header.cf = LV_IMG_CF_TRUE_COLOR;
        s.dsc.header.w  = ICON_W;
        s.dsc.header.h  = ICON_W;
        s.dsc.data_size = ICON_BYTES;
        s.dsc.data      = s.data;
    }
    cache_ok = true;
}

static IconSlot *find_slot(uint32_t hash) {
    for (int i = 0; i < ICON_SLOTS; i++)
        if (slots[i].hash == hash) return &slots[i];
    return nullptr;
}

// Emplacement libre, sinon le moins récemment utilisé (les 12 icônes affichées
// sont rafraîchies chaque seconde par icon_request_missing, donc jamais évincées).
static IconSlot *alloc_slot(uint32_t hash) {
    IconSlot *victim = &slots[0];
    for (int i = 0; i < ICON_SLOTS; i++) {
        if (slots[i].hash == 0) { victim = &slots[i]; break; }
        if (slots[i].last_use < victim->last_use) victim = &slots[i];
    }
    victim->hash     = hash;
    victim->mask     = 0;
    victim->ready    = false;
    victim->last_use = millis();
    victim->last_req = 0;
    return victim;
}

bool icon_store_chunk(const char *payload) {
    if (!cache_ok) return false;
    // "hhhhhhhh;idx;n;<base64>"
    char *end;
    uint32_t hash = strtoul(payload, &end, 16);
    if (hash == 0 || *end != ';') return false;
    long idx = strtol(end + 1, &end, 10);
    if (*end != ';' || idx < 0 || idx >= ICON_CHUNKS) return false;
    long n = strtol(end + 1, &end, 10);
    if (*end != ';' || n != ICON_CHUNKS) return false;
    const char *b64 = end + 1;

    IconSlot *s = find_slot(hash);
    if (s && s->ready) return false;   // déjà complète (renvoi en double)
    if (!s) s = alloc_slot(hash);

    size_t olen = 0;
    uint8_t *dst = s->data + idx * ICON_CHUNK_BYTES;
    if (mbedtls_base64_decode(dst, ICON_CHUNK_BYTES, &olen,
                              (const unsigned char *)b64, strlen(b64)) != 0
        || olen != ICON_CHUNK_BYTES)
        return false;   // morceau corrompu : sera renvoyé à la prochaine demande
    s->mask |= (uint8_t)(1u << idx);

    if (s->mask != 0xFF) return false;
    if (fnv1a32(s->data, ICON_BYTES) != hash) {
        s->mask = 0;     // contenu incohérent : on repart de zéro
        return false;
    }
    s->ready = true;
    return true;
}

const lv_img_dsc_t *icon_get(uint32_t hash) {
    if (!cache_ok || hash == 0) return nullptr;
    IconSlot *s = find_slot(hash);
    return (s && s->ready) ? &s->dsc : nullptr;
}

void icon_request_missing(const uint32_t *hashes, int n) {
    if (!cache_ok) return;
    uint32_t now = millis();
    for (int i = 0; i < n; i++) {
        uint32_t h = hashes[i];
        if (h == 0) continue;
        IconSlot *s = find_slot(h);
        if (!s) s = alloc_slot(h);
        s->last_use = now;
        if (s->ready) continue;
        if (s->last_req == 0 || now - s->last_req >= ICON_REQ_RETRY_MS) {
            s->last_req = now ? now : 1;
            Serial.printf("?I:%08lx\n", (unsigned long)h);
        }
    }
}
