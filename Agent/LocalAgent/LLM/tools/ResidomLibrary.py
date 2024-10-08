import sys
import time
from html import unescape
from typing import Any, Dict, Type, List
from urllib.parse import urlencode, urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from erniebot_agent.memory import HumanMessage, AIMessage, Message, FunctionMessage
from erniebot_agent.tools.base import Tool
from erniebot_agent.tools.schema import ToolParameterView
from lxml import html
from pydantic import Field
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

#
sys.path.insert(0, "../src")
sys.path.insert(0, "../../erniebot/src")
#
# 配置无头浏览器选项  主界面使用js异步加载 只能用selenium模拟浏览器爬取
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")


def search_books_by_title(title: str):
    """
    方法：通过url参数拼接 定位到搜索系统 且传入搜索参数
    attributes:
        title：传入为提示词识别到的书籍名称
    """
    base_url = "http://coin.lib.scuec.edu.cn/opac/openlink.php?"
    params = {
        "strSearchType": "title",
        "match_flag": "forward",
        "historyCount": "1",
        "strText": title,
        "doctype": "ALL",
        "with_ebook": "on",
        "displaypg": "20",
        "showmode": "list",
        "sort": "CATA_DATE",
        "orderby": "desc",
        "location": "ALL",
        "csrf_token": "KITmfnn0D3"
    }

    # 搜索索引拼接路由
    url = base_url + urlencode(params)

    # 伪装请求头  Cookie: 是我登录后的 cookie
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Cookie": "PHPSESSID=bree1igql274vkv55scom59877",
        "Host": "coin.lib.scuec.edu.cn",
        "Proxy-Connection": "keep-alive",
        "Referer": "http://coin.lib.scuec.edu.cn/opac/search.php",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()  # 检查请求是否成功

    return response.text


def parse_book_links(html_content):
    """
    方法 ： 解析出对应书籍主信息拼接字段
    """
    tree = html.fromstring(html_content)
    links = tree.xpath('//*[@id="search_book_list"]/li/h3/a/@href')
    return links


def get_full_urls(partial_urls):
    """
    方法 ：生成完整书籍路径
    """
    base_url = "http://coin.lib.scuec.edu.cn/opac/"
    full_urls = [urljoin(base_url, url.split('&')[0]) for url in partial_urls]
    return full_urls


# -------------------------------------------------图书馆图书推荐，基于搜索热度——————————————————————————————————————————————————————
# 图书热度排行推荐 prompt
class ScrapeBookInfoInput(ToolParameterView):
    """
    中南民族大学图书馆热搜URL http://coin.lib.scuec.edu.cn/top/top_lend.php?cls_no=ALL
    """
    arg: str = Field(description="根据借阅比或者借阅人数推荐图书  关键词 ：借阅比 ，借阅人数")


# Agent输出结构 result
class BookInfoOutput(ToolParameterView):
    rank: str = Field(description="借阅热度排名")
    title: str = Field(description="书名")
    author: str = Field(description="作者")
    publisher: str = Field(description="出版社")
    call_number: str = Field(description="索书号")
    collection_count: str = Field(description="馆藏")
    borrowing_count: str = Field(description="借阅次数")
    borrowing_ratio: str = Field(description="借阅比")


class ScrapeBookInfoTool(Tool):
    """
    实现智能体热度查询
    """
    description: str = "通过关键词 借阅比 借阅人数 查询书本信息"
    input_type: Type[ToolParameterView] = ScrapeBookInfoInput
    output_type: Type[ToolParameterView] = List[BookInfoOutput]

    async def __call__(self, arg: str) -> Dict[str, Any]:
        url ="http://coin.lib.scuec.edu.cn/top/top_lend.php?cls_no=ALL"
        response = requests.get(url)
        response.raise_for_status()

        tree = html.fromstring(response.content)
        xpath = "//tr[td[@class='whitetext']]"
        rows = tree.xpath(xpath)

        books = []
        if rows:
            for idx, row in enumerate(rows[:10], start=1):  # 只提取前十本书
                cells = row.xpath("td[@class='whitetext']")
                if len(cells) == 8:
                    book_info = {
                        id: idx,
                        "rank": unescape(cells[0].text_content().strip()),
                        "title": unescape(cells[1].text_content().strip()),
                        "author": unescape(cells[2].text_content().strip()),
                        "publisher": unescape(cells[3].text_content().strip()),
                        "call_number": unescape(cells[4].text_content().strip()),
                        "collection_count": unescape(cells[5].text_content().strip()),
                        "borrowing_count": unescape(cells[6].text_content().strip()),
                        "borrowing_ratio": unescape(cells[7].text_content().strip())
                    }
                    books.append(book_info)

        return {"result": f"已经为您推荐中南民族大学图书,根据借阅比，推荐图书如下：{books}"}
    @property
    def examples(self) -> List[Message]:
        return [
            HumanMessage(content="可以根据借阅人数来为我推荐书籍吗"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想根据 借阅人数 推荐书籍，我可以使用{self.tool_name}工具来获取推荐信息",
                    "arguments": '{"arg":"借阅人数"}',
                },
            ),
            FunctionMessage(name=f'{self.tool_name}', content=(
                '{"result":"已经为您推荐中南民族大学图书,根据借阅比，推荐图书如下：xxxxxxxxxxxxxxxxxxx"}')),
            AIMessage(content=(
                '{"result":"已经为您推荐中南民族大学图书,根据借阅比，推荐图书如下：xxxxxxxxxxxxxxxxxxx"}')),

            HumanMessage("帮我推荐一些书 最好根据借阅比"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想根据借阅比来推荐书籍，我可以使用{self.tool_name}来获取热门评分书籍信息",
                    "arguments": '{"arg":"借阅比"}',
                },
            ),
            FunctionMessage(name=f"{self.tool_name}", content=(
                '{"result":"已经为您推荐中南民族大学图书,根据借阅比，推荐图书如下：xxxxxxxxxxxxxxxxxxx"}"}')),
            AIMessage(content=(
                '{"result":"）"已经为您推荐中南民族大学图书,根据借阅比，推荐图书如下：xxxxxxxxxxxxxxxxxxx"}')),
        ]


# -------------------------------------------------图书馆图书推荐，基于搜索热度——————————————————————————————————————————————————————

# 用户询问图书状态
class GetBookIDInfoPut(ToolParameterView):
    name: str = Field(description="通过书名查询指定图书信息")


# 智能体输出结构 result
class ResearchBookResultOutput(ToolParameterView):
    book_status: str = Field(description="书本状态 两种状态 值为 可借  其他为不可借阅")
    location: str = Field(description="藏书位置")
    get_book: str = Field(description="索书号")


class ReseachBookMessageTool(Tool):
    description: str = "从指定路由中爬取书籍信息"
    input_type: Type[ToolParameterView] = GetBookIDInfoPut
    output_type: Type[ToolParameterView] = List[ResearchBookResultOutput]

    async def __call__(self, name: str) -> Dict[str, Any]:
        search_result_html = search_books_by_title(name)
        book_links = parse_book_links(search_result_html)
        full_urls = get_full_urls(book_links)
        print(full_urls)
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(full_urls[0])
        time.sleep(5)  # 等待 5 秒
        page_content = driver.page_source
        driver.quit()
        tree = html.fromstring(page_content)
        rows = tree.xpath('//tr[@align="left" and contains(@class, "whitetext")]')
        book_message_list = []
        index = 1  # 独立编号
        for row in rows:
            cells = row.xpath('./td')
            if len(cells) >= 8:
                status = cells[4].text_content().strip()
                if '可借' in status:
                    data = {
                        'id': index,
                        'get_book': cells[0].text_content().strip(),
                        'book_status': status,
                        'location': cells[5].xpath('./iframe/@src')[0] if cells[5].xpath('./iframe/@src') else None,
                    }
                    book_message_list.append(data)
                    index += 1
        return {"result": f"找到{name}的信息：{book_message_list}"}

    @property
    def examples(self) -> List[Message]:
        return [
            HumanMessage(content="斗罗大陆 这本书目前可以借阅吗"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想知道 斗罗大陆 这本书的情况，我可以使用{self.tool_name}工具来获取该书的信息，并从中获取书籍位置 借阅状态",
                    "arguments": '{"name":"斗罗大陆"}',
                },
            ),
            FunctionMessage(name="ReseachBookMessageTool", content=(
                '{"result":"您好，斗罗大陆 这本书目前有多个可借的副本。以下是部分副本的借阅信息：1. 编号：I247.5/0031/  10，状态：可借，位置：[链接]("http://210.42.146.25:8081/Default.aspx?BookID=1862332")2. 编号：I247.5/0031/  10，状态：可借，位置：[链接](""http://210.42.146.25:8081/Default.aspx?BookID=1862328)...（注：这里只列出了部分副本的借阅信息，您可以选择其中一个位置进行借阅）"}')),
            AIMessage(content=(
                '{"result":"您好，斗罗大陆 这本书目前有多个可借的副本。以下是部分副本的借阅信息：1. 编号：I247.5/0031/  10，状态：可借，位置：[链接]("http://210.42.146.25:8081/Default.aspx?BookID=1862332")2. 编号：I247.5/0031/  10，状态：可借，位置：[链接](""http://210.42.146.25:8081/Default.aspx?BookID=1862328)...（注：这里只列出了部分副本的借阅信息，您可以选择其中一个位置进行借阅）"}')),

            HumanMessage("去哪里可以借阅 明朝那些事儿"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想知道 明朝那些事儿 在哪里可以借阅，我可以使用{self.tool_name}来获取概述信息，并且提取书籍位置 借阅状态",
                    "arguments": '{"name":"明朝那些事儿"}',
                },
            ),
            FunctionMessage(name="ReseachBookMessageTool", content=(
                '{"result":"您好，明朝那些事儿 这本书目前有多个可借的副本。以下是部分副本的借阅信息：1. 编号：I247.5/0031/  10，状态：可借，位置：[链接]("http://210.42.146.25:8081/Default.aspx?BookID=1862332")2. 编号：I247.5/0031/  10，状态：可借，位置：[链接](""http://210.42.146.25:8081/Default.aspx?BookID=1862328)...（注：这里只列出了部分副本的借阅信息，您可以选择其中一个位置进行借阅）"}')),
            AIMessage(content=(
                '{"result":"您好，明朝那些事儿 这本书目前有多个可借的副本。以下是部分副本的借阅信息：1. 编号：I247.5/0031/  10，状态：可借，位置：[链接]("http://210.42.146.25:8081/Default.aspx?BookID=1862332")2. 编号：I247.5/0031/  10，状态：可借，位置：[链接](""http://210.42.146.25:8081/Default.aspx?BookID=1862328)...（注：这里只列出了部分副本的借阅信息，您可以选择其中一个位置进行借阅）"}')),
        ]


# 用户询问图书状态
class BookRecommdInput(ToolParameterView):
    arg: str = Field(description="根据大众评分推荐图书  关键词大众评分")


# 智能体输出结构 result
class BookRecommdOutPut(ToolParameterView):
    result: str = Field(description="返回检索信息")


def DecideCategory(arg: str):
    if arg == "热门评分":
        return "top_score.php"
    elif arg == "热门收藏":
        return "top_shelf.php"
    elif arg == "热门图书":
        return "top_book.php"


class MutilRecommdBooksTool(Tool):
    description: str = "根据大众评分图书推荐"
    input_type: Type[ToolParameterView] = BookRecommdInput
    output_type: Type[ToolParameterView] = BookRecommdOutPut

    async def __call__(self, arg: str) -> Dict[str,Any]:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        driver = webdriver.Chrome(options=chrome_options)

        try:
            category = DecideCategory("热门评分")
            full_url = "http://coin.lib.scuec.edu.cn/top/" + f"{category}"
            driver.get(url=full_url)
            books = []
            wait = WebDriverWait(driver, 10)
            rows = driver.find_elements(By.XPATH, '//*[@id="container"]/table/tbody/tr')

            for index, row in enumerate(rows[1:21], start=1):  # 从第二个tr开始遍历
                # 获取当前tr下的所有td元素
                cells = row.find_elements(By.TAG_NAME, 'td')

                # 确保有足够的td元素
                if len(cells) >= 7:
                    book_info = {
                        'top_num': cells[0].text.strip(),
                        'book_name': cells[1].text.strip(),
                        'author': cells[2].text.strip(),
                        'publish': cells[3].text.strip(),
                        'predict_people': cells[6].text.strip()
                    }
                    books.append(book_info)
            # 打印结果
            recommendations = "根据大众评分为您推荐以下书籍：\n"
            for book in books:
                recommendation = f"排名：{book['top_num']}，书籍：{book['book_name']}，作者：{book['author']}，出版社：{book['publish']}，评价人数：{book['predict_people']}\n"
                recommendations += recommendation
            return {"result":f"{recommendations}"}

        finally:
            driver.quit()


    @property
    def examples(self) -> List[Message]:
        return [
            HumanMessage(content="可以根据大众评分来为我推荐书籍吗"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想根据 大众评分推荐书籍，我可以使用{self.tool_name}工具来获取推荐信息",
                    "arguments": '{"arg":"大众评分"}',
                },
            ),
            FunctionMessage(name=f'{self.tool_name}', content=(
                '{"result":"根据大众评分为您推荐以下书籍：xxxxxxxxxxxxxxxxxxx"}')),
            AIMessage(content=(
                '{"result":"根据大众评分为您推荐以下书籍：xxxxxxxxxxxxxxxxxxx"}')),

            HumanMessage("帮我推荐一些书 最好是热门评分的"),
            AIMessage(
                "",
                function_call={
                    "name": self.tool_name,
                    "thoughts": f"用户想根据热门评分来推荐书籍，我可以使用{self.tool_name}来获取热门评分书籍信息",
                    "arguments": '{"arg":"热门评分"}',
                },
            ),
            FunctionMessage(name=f"{self.tool_name}", content=(
                '{"result":"根据大众评分为您推荐以下书籍(前二十名)：xxxxxxxxxxxxxxxxxxx"}"}')),
            AIMessage(content=(
                '{"result":"）"根据大众评分为您推荐以下书籍(前二十名)：xxxxxxxxxxxxxxxxxxx"}')),
        ]

