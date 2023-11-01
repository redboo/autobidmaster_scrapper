import argparse
import ast
import asyncio
import os
import random
from argparse import Namespace
from platform import system
from time import sleep

import aiohttp
import pandas as pd
from dotenv import load_dotenv
from icecream import ic
from pandas import DataFrame
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

load_dotenv()

EMAIL: str | None = os.getenv("EMAIL")
PASSWORD: str | None = os.getenv("PASSWORD")

OUTPUT_FILE_PATH = "downloads/data.csv"
BASE_URL = "https://www.autobidmaster.com/ru/"


def initialize_driver() -> WebDriver:
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    current_directory: str = os.getcwd()
    driver_directory: str = os.path.join(current_directory, "driver")
    chromedriver_filename: str = "chromedriver.exe" if system() == "Windows" else "chromedriver"
    chromedriver_path: str = os.path.join(driver_directory, chromedriver_filename)

    service = ChromeService(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=options)


def save_to_csv(dataframe, output_file_path) -> None:
    dataframe.to_csv(output_file_path, index=False, encoding="utf-8")


def fetch_data(driver, filter_params, pages: int) -> DataFrame:
    page = 1
    all_data = []

    while page < pages + 1:
        data_search_url: str = (
            f"{BASE_URL}data/v2/inventory/search?custom_search=quickpick-runs-and-drives%2F"
            f"year-{filter_params['year_range']}%2F&size={filter_params['page_size']}"
            f"&page={page}&sort={filter_params['sort_by']}&order={filter_params['sort_order']}"
        )

        driver.get(data_search_url)
        json_data = driver.execute_script("return JSON.parse(document.body.innerText);")

        total_cars = json_data.get("total", 0)
        all_data.extend(json_data.get("lots", []))

        page += 1
        if page * filter_params["page_size"] > total_cars:
            break

        sleep(random.uniform(1.0, 3.0))

    return pd.DataFrame(all_data)


def process_dataframe(df: DataFrame) -> DataFrame:
    columns_to_keep: list[str] = [
        "vehicleCategory",
        "year",
        "make",
        "model",
        "modelGroup",
        "vin",
        "color",
        "description",
        "images",
        "primaryDamage",
        "secondaryDamage",
        "title",
        "odometerType",
        "odometerBrand",
        "engineSize",
        "drive",
        "transmission",
        "fuel",
        "id",
        "odometer",
        "cylinders",
        "saleStatusString",
        "locationName",
        "sold",
        "largeImage",
        "currentBid",
    ]

    try:
        df = df[columns_to_keep]
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        raise

    return df


async def download_image(session, image_url, file_path) -> None:
    async with session.get(image_url) as response:
        with open(file_path, "wb") as f:
            while True:
                chunk = await response.content.read(8192)
                if not chunk:
                    break
                f.write(chunk)


async def download_images(images, output_folder="downloads/images") -> None:
    ic()
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for image_url in images:
            file_name: str = os.path.join(output_folder, f"{image_url.split('/')[-1]}")
            if not os.path.exists(file_name):
                tasks.append(download_image(session, image_url, file_name))
            else:
                ic(f"Файл {file_name} уже существует. Пропускаем загрузку.")

        await asyncio.gather(*tasks)


def process_images(images) -> list[str]:
    def get_image_url(item):
        return item["hdr"] if item["hdr"] is not None else item["full"]

    return [get_image_url(item) for item in ast.literal_eval(images)]


def process_images_column(output_file_path) -> list[str]:
    ic()
    df: DataFrame = pd.read_csv(output_file_path)
    df["images"] = df["images"].apply(process_images)
    all_images: list[str] = [image for sublist in df["images"] for image in sublist]
    df.to_csv(output_file_path, index=False, encoding="utf-8")

    return all_images


async def main(pages: int) -> None:
    ic(pages)
    driver: WebDriver = initialize_driver()

    try:
        script = """
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """
        driver.execute_script(script)

        driver.minimize_window()
        driver.get(f"{BASE_URL}login")

        email_field: WebElement = driver.find_element(By.ID, "email")
        email_field.send_keys(EMAIL)

        password_field: WebElement = driver.find_element(By.ID, "password")
        password_field.send_keys(PASSWORD)
        password_field.send_keys(Keys.RETURN)
        sleep(2)

        filter_params: dict[str, str | int] = {
            "year_range": "2021-2024",
            "page_size": 100,
            "sort_by": "sale_date",
            "sort_order": "asc",
        }

        df: DataFrame = fetch_data(driver, filter_params, pages)
        df = process_dataframe(df)
        save_to_csv(df, OUTPUT_FILE_PATH)
        image_list: list[str] = process_images_column(OUTPUT_FILE_PATH)
        await download_images(image_list)

    except Exception as e:
        print(f"Произошла ошибка: {e}")

    finally:
        driver.close()
        driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Скраппинг данных с Autobidmaster")
    parser.add_argument("pages", type=int, nargs="?", default=1, help="Количество страниц для обработки")
    args: Namespace = parser.parse_args()
    asyncio.run(main(args.pages))
