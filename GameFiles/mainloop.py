import pygame as pg
import sys
from startScreen import *
from mainGame import *

pg.init()


clock = pg.time.Clock()
window_width = 1600
window_height = 800
screen = pg.display.set_mode((window_width,window_height), pg.SCALED | pg.RESIZABLE)
dt = 0


def endScreen():
    pass


while True:
    #Basic Handling
    for event in pg.event.get():
        if event.type == pg.QUIT:
            pg.quit()
            sys.exit()
        if event.type == pg.KEYDOWN:
            full = pg.display.is_fullscreen()
            if event.key == pg.K_F11 or (event.key == pg.K_ESCAPE and full):
                pg.display.toggle_fullscreen()
    difficulty = startScreen(screen, window_width, window_height, clock)
    
    mainGame(screen, window_width, window_height, clock, difficulty)
                
                
                
                
                
                
                
                
    pg.display.update()
    dt = clock.tick(60)/1000