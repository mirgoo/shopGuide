# _*_ coding: utf-8 _*_

import jieba
import jieba.analyse
import time
import threading

from spider import jd
from spider import amazon
from sql import db

from ipdb import set_trace

jieba.load_userdict('mydict')


def Search(limit_price, key_word, page_num=1):
    assert type(limit_price) == float
    a_spider = amazon.Amazon()
    j_spider = jd.JD()
    # Amazon爬虫返回的结果格式为一个字典，像这样{A_name: (A_url, A_price), B_name: (B_url, B_price), ...}
    a_results = a_spider.search(key_word, page_num)
    for name in a_results.keys():
        # 筛选用户大于设定价格的的商品，如果价格小于设定的价格就弹出
        if a_results[name][1] < limit_price:
            a_results.pop(name)

    # 以价格为排序, 将得到一个列表[(a_name, (a_url, a_price)), ...]
    results = sorted(a_results.items(), key=lambda item: item[1][1])

    # 想要用多线程进行查找相同商品，必须要先把Amazon的结果进行分组，每组商品由一个线程去处理
    # 避免出现商品数量少于线程数报错(出现分组长度为0)
    t = len(a_results) / 8 if len(a_results) >= 8 else 1
    Threads = []
    Result = []
    for a_goodses in list(results[i:i+t] for i in xrange(0, len(results), t)):
        Threads.append(threading.Thread(target=search_same, args=(j_spider, key_word, a_goodses, Result, )))
    for Thread in Threads:
        Thread.start()
    for Thread in Threads:
        Thread.join()
    return Result


def search_same(j_spider, key_word, a_goodses, Result):
    # a_goodses 的结构为:[(a_name, (a_url, a_price)), ...]
    for a_goods in a_goodses:
        a_name = a_goods[0]
        a_url = a_goods[1][0]
        a_price = a_goods[1][1]
        search_word = extract_tags(key_word, a_name)
        assert type(a_price) == float
        old_data = db.find_one_goods(key_word, a_name)
        today = int(time.strftime("%Y%m%d"))
        if old_data and 'prices' in old_data.keys() and old_data['prices'][-1]['date'] == today:
            Result.append(old_data)
            continue
        try:
            # 以Amazon的商品价格作为期望价格(0.9~1.1)做限定价格去搜索JD商品
            j_results = j_spider.search(a_price, search_word)
            # 如果搜索不到尝试反转搜索关键词
            if len(j_results) == 0:
                j_results = j_spider.search(a_price, ' '.join(search_word.split()[::-1]))
            same_goods = chose_result(a_price, j_results)
            data = {'name': a_name, 'key_word': key_word, 'url': a_url, 'price': a_price, 'same': same_goods}
            Result.append(db.save_search_result(data))
        except:
            continue


def extract_tags(key_word, a_name):
    '''
    根据商品名分词取前十个, 利用分析模块解析出关键字,提取相同部分,
    最后并集得出应该在JD搜索的关键字, 关键字数量不应该超过5个避免搜索结果出不来,
    针对搜索的商品名字类别，可以添加自定义词典提高准确度（后再加）
    '''
    cut_tags = [tag for tag in jieba.cut(a_name)][:8]
    analyse_tags = jieba.analyse.extract_tags(a_name)
    tags = [tag for tag in cut_tags if tag in analyse_tags]
    # 把亚马逊搜索的关键字拼接到tags第一位
    try:
        tags.remove(key_word)
    except:
        pass
    tags.insert(0, key_word)
    if len(tags) > 5:
        tags = tags[:5]
    return ' '.join(tags)


def chose_result(a_price, j_results):
    assert type(a_price) == float
    assert type(j_results) == dict
    '''
    对结果字典按照value进行排序
    如果结果长度大于二，则返回最低价和第一个大于等于amazon价格的结果项的列表,
    但要避免最低价就是第一个大于amazon价格的, 否则返回空列表
    '''
    results = sorted(j_results.items(), key=lambda item: item[1][1])
    if len(results) >= 2:
        min_result = results[0]
        gt_result = [result for result in results if result[1][1] >= a_price][0]
        one_list = [{'j_name': min_result[0], 'url': min_result[1][0], 'price': min_result[1][1]}]
        two_list = [{'j_name': min_result[0], 'url': min_result[1][0], 'price': min_result[1][1]},
                    {'j_name': gt_result[0], 'url': gt_result[1][0], 'price': gt_result[1][1]}]
        if not gt_result:
            return one_list
        elif gt_result == min_result:
            return one_list
        else:
            return two_list
    elif len(results) == 1:
        return one_list
    else:
        return []
