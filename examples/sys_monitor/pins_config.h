#pragma once

// Brochage T-Display-S3-Long, révision à tactile CST3530 (voir README, « Hardware »)

#define SPI_FREQUENCY         32000000
#define TFT_SPI_MODE          SPI_MODE0
#define TFT_SPI_HOST          SPI2_HOST

#define EXAMPLE_LCD_H_RES     180
#define EXAMPLE_LCD_V_RES     640

#define SEND_BUF_SIZE         (28800/2) // pixels par transaction DMA (16 bits RGB565)

// Écran AXS15231B (QSPI)
#define TFT_QSPI_CS           12
#define TFT_QSPI_SCK          17
#define TFT_QSPI_D0           13
#define TFT_QSPI_D1           18
#define TFT_QSPI_D2           21
#define TFT_QSPI_D3           14
#define TFT_QSPI_RST          16
#define TFT_BL                1

// Tactile CST3530 (I2C, partagé avec le chargeur BQ25896 en 0x6A)
#define TOUCH_IICSCL          10
#define TOUCH_IICSDA          15
#define TOUCH_INT             11
#define TOUCH_RES             2

#define PIN_BUTTON_1          0   // bouton BOOT
