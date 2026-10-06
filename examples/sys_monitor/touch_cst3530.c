#include "touch_cst3530.h"
#include "hyn_core.h"
#include "esp_timer.h"

// Le pilote lit les points dans sa propre tâche, sur front descendant de INT.
// Si le rapport de levée du doigt était perdu, rep_num resterait > 0 : on ne
// considère le doigt posé que si une interruption est arrivée récemment.
#define CST_STALE_MS 200

static struct hyn_ts_data *ts = NULL;
static uint32_t last_irq_ms = 0;

void cst3530_begin(int sda, int scl, int irq, int rst)
{
    touch_init(sda, scl, irq, rst);   // HYN_POWER_ON_UPDATA = 0 : aucune écriture en flash
    ts = get_touch_data();
}

int cst3530_read(uint16_t *x, uint16_t *y)
{
    if (ts == NULL) return 0;
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    if (ts->hyn_irq_flg) {
        ts->hyn_irq_flg = 0;
        last_irq_ms = now;
    }
    if (ts->rp_buf.rep_num == 0 || now - last_irq_ms > CST_STALE_MS) return 0;
    *x = ts->rp_buf.pos_info[0].pos_x;
    *y = ts->rp_buf.pos_info[0].pos_y;
    return 1;
}

