#pragma once
#include <lvgl.h>
#include "serial_parser.h"

void ui_init(void);
void ui_update(const SysData *data);
void ui_show_no_signal(void);
