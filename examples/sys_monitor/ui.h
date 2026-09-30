#pragma once
#include <lvgl.h>
#include "serial_parser.h"

void ui_init(void);
void ui_update(const SysData *data);
void ui_show_no_signal(void);

// Écran 2 : top processus (bascule au toucher)
void ui_toggle_page(void);
void ui_update_procs(const ProcData *p);
void ui_refresh_proc_icons(void);   // une icône vient d'arriver : remplace la pastille
