#pragma once
#include <stdint.h>

// Tactile CST3530 (Hynitron) des T-Display-S3-Long récentes (branche LilyGo
// T-Display-S3-Long-cst3530, mai 2026). Enveloppe le pilote lib/hyn_driver_for_esp32
// dont l'en-tête redéfinit bool/NULL/HIGH/TRUE : il ne doit pas entrer dans le .ino.

#ifdef __cplusplus
extern "C" {
#endif

void cst3530_begin(int sda, int scl, int irq, int rst);

// 1 si un doigt est posé (coordonnées dans *x, *y), 0 sinon
int cst3530_read(uint16_t *x, uint16_t *y);

#ifdef __cplusplus
}
#endif
