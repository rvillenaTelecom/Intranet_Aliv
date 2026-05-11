from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

opciones = webdriver.ChromeOptions()
opciones.add_argument('--no-sandbox')
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opciones)
wait = WebDriverWait(driver, 15)

try:
    driver.get('https://alivtelecom.com/alivsistemaventas/index2.php')
    time.sleep(2)
    driver.switch_to.frame('abajo')
    
    driver.find_element(By.ID, 'usuario').send_keys('rramirez')
    driver.find_element(By.ID, 'clave').send_keys('NUEVO2025')
    driver.execute_script('Procesa();')
    
    time.sleep(4)
    # Check if we need to switch to default content or another frame after login
    driver.switch_to.default_content()
    # It might still be framed
    try:
        driver.switch_to.frame('abajo')
    except:
        pass
        
    html = driver.page_source
    with open('aliv_menu.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('HTML de menu guardado')
except Exception as e:
    print('Error:', e)
finally:
    driver.quit()
