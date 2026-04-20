from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import os
import json
import csv

def create_driver():
    options = Options()
    options.add_argument('--start-maximized')
    options.add_experimental_option("detach", True)

    driver = webdriver.Chrome(options=options)
    return driver

def search_keyword(driver, keyword):
    search_input = driver.find_element(By.NAME, "txtKW")
    search_input.send_keys(keyword)
    search_input.send_keys(Keys.RETURN)
        
def click_article(driver, length,wait):
    jud_data = []
    
    for i in range(length):
        
            driver.switch_to.default_content() 
            wait.until(EC.presence_of_element_located((By.ID, "iframe-data")))
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
            
            case_link_roll = wait.until(EC.element_to_be_clickable((By.XPATH, f"(//a[contains(@class, 'hlTitle_scroll')])[{i+1}]")))
            driver.execute_script("arguments[0].click();", case_link_roll)
            
            print(f"成功點擊第 {i+1} 篇判決書")
            print("="*30)
            
            driver.switch_to.default_content()
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
            
            case_id_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "col-td")))
            case_id = case_id_element.text.strip()
            
                
            jud_text = wait.until(EC.presence_of_element_located((By.ID, "jud"))).text
            print("\n=== 判決書內容擷取成功 ===")
            
            case_data = {
                "case_id":case_id,
                "case_content": jud_text
            }
            
            jud_data.append(case_data)
            
            print(f"成功儲存判決書{i+1}內容")
            print("="*30)
            driver.back()
            
            time.sleep(1)
            
    dump_json(jud_data)
    
def click_next_page(driver,wait):
    driver.switch_to.default_content()
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
    
    next_page_botton = wait.until(EC.element_to_be_clickable((By.ID, "hlNext")))
    next_page_botton.click()
    
    time.sleep(3)
    
def dump_json(data):
    num=1
    
    target_path = f'data/trainning_data_set/judgment_{num}.json'
    
    if os.path.exists(target_path):
        with open(target_path, 'a', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    else:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    num+=1
    
def main():
    driver = create_driver()
    wait = WebDriverWait(driver, 10)

    judge_url = 'https://judgment.judicial.gov.tw/FJUD/default.aspx'
    driver.get(judge_url)
    
    web_pages = int(input("請輸入要爬取的頁數: "))
    
    i = 0
    
    search_keyword(driver, '桃園地方法院')

    print('='*30)
    print("等待結果")
    
    while i < web_pages:
        driver.switch_to.default_content()
        wait.until(EC.presence_of_element_located((By.ID, "iframe-data")))

        driver.switch_to.frame("iframe-data")
        
        case_links = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "hlTitle_scroll")))
        total_cases = len(case_links)
        print(f"本頁共有 {total_cases} 篇判決書")
        
        click_article(driver, total_cases, wait)
        
        if web_pages > 1 and i < web_pages - 1:
            click_next_page(driver, wait)
        
        i+=1
        
        print(f"開始爬取第 {i+1} 頁")
        
    driver.quit()
        
if __name__ == '__main__':
    main()
