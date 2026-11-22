import pygame as pg
import sys

def startScreen(screen, window_width, window_height, clock):
    
    title = pg.font.Font(None, int(72*window_width/800)).render('Alphabet Blast', True, 'white')
    prompt = pg.font.Font(None, int(32*window_width/400)).render('Select Difficulty', True, 'white')
    easy_button = pg.font.Font(None, int(32*window_width/400)).render('Easy', True, 'white')
    hard_button = pg.font.Font(None, int(32*window_width/400)).render('Hard', True, 'white')
    easy_button_rect = easy_button.get_rect(center = (window_width/3, window_height*0.7))
    hard_button_rect = hard_button.get_rect(center = (window_width*2/3, window_height*0.7))
    mouse_x = 0
    mouse_y = 0
    
    while True:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit()
                sys.exit()
            if event.type == pg.KEYDOWN:
                full = pg.display.is_fullscreen()
                if event.key == pg.K_F11 or (event.key == pg.K_ESCAPE and full):
                    pg.display.toggle_fullscreen()
            if event.type == pg.MOUSEBUTTONDOWN and easy_button_rect.collidepoint(mouse_x, mouse_y):
                return 'Easy'
            if event.type == pg.MOUSEBUTTONDOWN and hard_button_rect.collidepoint(mouse_x, mouse_y):
                return 'Hard'
                    
        screen.blit(title, title.get_rect(center=(window_width/2, window_height*.375)))
        screen.blit(prompt, prompt.get_rect(center=(window_width/2, .5*window_height)))
        screen.blit(easy_button, easy_button_rect)
        screen.blit(hard_button, hard_button_rect)
       
        mouse_x, mouse_y = pg.mouse.get_pos()
        
        if easy_button_rect.collidepoint(mouse_x, mouse_y):
            easy_button = pg.font.Font(None, int(32*window_width/400)).render('Easy', True, 'red')
        else:
            easy_button = pg.font.Font(None, int(32*window_width/400)).render('Easy', True, 'white')
            
        if hard_button_rect.collidepoint(mouse_x, mouse_y):
            hard_button = pg.font.Font(None, int(32*window_width/400)).render('Hard', True, 'red')
        else:
            hard_button = pg.font.Font(None, int(32*window_width/400)).render('Hard', True, 'white')
            
        pg.display.update()
        dt = clock.tick(60)/1000