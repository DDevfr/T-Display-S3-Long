#pragma once
#include <lvgl.h>

// Icônes d'applis de l'écran 2 : 32×32 RGB565 big-endian (LV_COLOR_16_SWAP=1),
// reçues du PC en 8 morceaux de 256 octets (trames "I:h;idx;n;<base64>"),
// identifiées par le hash FNV-1a 32 de leur contenu.
#define ICON_W       32
#define ICON_BYTES   (ICON_W * ICON_W * 2)
#define ICON_CHUNKS  8
#define ICON_CHUNK_BYTES (ICON_BYTES / ICON_CHUNKS)

void icon_cache_init(void);

// `payload` pointe après "I:". Renvoie true quand l'icône devient complète et valide.
bool icon_store_chunk(const char *payload);

// Icône prête, ou nullptr (pas encore reçue / hash 0).
const lv_img_dsc_t *icon_get(uint32_t hash);

// Envoie « ?I:<hash> » pour chaque icône absente (max 1 fois / 2 s / hash)
// et marque les icônes affichées comme récemment utilisées.
void icon_request_missing(const uint32_t *hashes, int n);
