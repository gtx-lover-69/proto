from machine import Pin, SoftSPI
from ST7735 import TFT
from sysfont import sysfont
 
LCD_SDA = 2
LCD_SCL = 3
LCD_CS = 0
LCD_DC = 1
 
spi = SoftSPI(baudrate=8_000_000, polarity=0, phase=0,
              sck=Pin(LCD_SCL), mosi=Pin(LCD_SDA), miso=Pin(12))
 
tft = TFT(spi, LCD_DC, LCD_RST, LCD_CS)
tft.initr()
tft.rgb(True)
tft.fill(TFT.BLACK)
tft.text((4, 4), "Hello, world!", TFT.WHITE, sysfont, 2, nowrap=True)
 
