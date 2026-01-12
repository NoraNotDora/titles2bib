# coding:utf-8
"""
辅助检索模块：当dblp搜索失败时，使用arxiv和google scholar作为备选
"""
import requests
import xml.etree.ElementTree as ET
import re
import time

# ==================== arxiv API ====================

def search_arxiv(title, max_results=1):
    """
    使用arxiv API搜索论文
    返回BibTeX格式字符串，失败返回None
    """
    try:
        # 清理标题中的特殊字符
        clean_title = re.sub(r'[^\w\s]', ' ', title)
        clean_title = ' '.join(clean_title.split())
        
        # arxiv API查询
        base_url = 'http://export.arxiv.org/api/query'
        params = {
            'search_query': f'ti:"{clean_title}"',
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance'
        }
        
        response = requests.get(base_url, params=params, timeout=30)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None
        
        # 解析XML响应
        root = ET.fromstring(response.text)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 
              'arxiv': 'http://arxiv.org/schemas/atom'}
        
        entries = root.findall('atom:entry', ns)
        if not entries:
            return None
        
        entry = entries[0]
        
        # 提取信息
        entry_title = entry.find('atom:title', ns)
        if entry_title is None:
            return None
        entry_title = ' '.join(entry_title.text.split())
        
        # 验证标题相似度
        if not _title_similar(title, entry_title):
            return None
        
        # 提取其他信息
        authors = entry.findall('atom:author/atom:name', ns)
        author_list = [a.text for a in authors]
        
        published = entry.find('atom:published', ns)
        year = published.text[:4] if published is not None else ''
        
        arxiv_id_elem = entry.find('atom:id', ns)
        arxiv_id = arxiv_id_elem.text.split('/')[-1] if arxiv_id_elem is not None else ''
        # 移除版本号
        arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
        
        summary = entry.find('atom:summary', ns)
        
        # 检查是否有DOI（可能已发表）
        doi_elem = entry.find('arxiv:doi', ns)
        doi = doi_elem.text if doi_elem is not None else None
        
        # 检查是否有journal_ref（可能已发表）
        journal_ref_elem = entry.find('arxiv:journal_ref', ns)
        journal_ref = journal_ref_elem.text if journal_ref_elem is not None else None
        
        # 生成BibTeX
        bibtex = _format_arxiv_bibtex(arxiv_id, entry_title, author_list, year, doi, journal_ref)
        return bibtex
        
    except Exception as e:
        print(f"  [arxiv] 搜索出错: {e}")
        return None


def _title_similar(title1, title2, threshold=0.7):
    """简单的标题相似度检查"""
    def normalize(s):
        return set(re.findall(r'\w+', s.lower()))
    
    words1 = normalize(title1)
    words2 = normalize(title2)
    
    if not words1 or not words2:
        return False
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union) >= threshold


def _format_arxiv_bibtex(arxiv_id, title, authors, year, doi=None, journal_ref=None):
    """将arxiv信息格式化为BibTeX字符串"""
    # 生成cite key
    first_author_lastname = authors[0].split()[-1] if authors else 'Unknown'
    cite_key = f"arxiv:{first_author_lastname}{year}"
    
    # 格式化作者
    author_str = ' and\n               '.join(authors)
    
    # 构建BibTeX
    bibtex_lines = [
        f"@article{{{cite_key},",
        f"  author    = {{{author_str}}},",
        f"  title     = {{{{{title}}}}},",
        f"  journal   = {{arXiv preprint arXiv:{arxiv_id}}},",
        f"  year      = {{{year}}}"
    ]
    
    bibtex_lines.append("}")
    
    return '\n'.join(bibtex_lines) + '\n'


# ==================== Google Scholar ====================

def search_google_scholar(title, max_results=1):
    """
    使用scholarly库搜索Google Scholar
    返回BibTeX格式字符串，失败返回None
    
    注意：需要安装 scholarly 库: pip install scholarly
    """
    try:
        from scholarly import scholarly
    except ImportError:
        print("  [Google Scholar] 未安装scholarly库，跳过。可通过 pip install scholarly 安装")
        return None
    
    try:
        # 搜索论文
        search_query = scholarly.search_pubs(title)
        
        # 获取第一个结果
        result = next(search_query, None)
        if result is None:
            return None
        
        # 验证标题相似度
        result_title = result.get('bib', {}).get('title', '')
        if not _title_similar(title, result_title):
            return None
        
        # 提取BibTeX信息
        bib = result.get('bib', {})
        
        authors = bib.get('author', ['Unknown'])
        if isinstance(authors, str):
            authors = [authors]
        
        year = bib.get('pub_year', '')
        venue = bib.get('venue', bib.get('journal', bib.get('booktitle', '')))
        
        # 生成cite key
        first_author_lastname = authors[0].split()[-1] if authors else 'Unknown'
        cite_key = f"scholar:{first_author_lastname}{year}"
        
        # 判断文献类型
        pub_type = 'article'
        if 'conference' in venue.lower() or 'proceedings' in venue.lower() or 'symposium' in venue.lower():
            pub_type = 'inproceedings'
        
        # 格式化作者
        author_str = ' and\n               '.join(authors)
        
        # 构建BibTeX
        bibtex_lines = [
            f"@{pub_type}{{{cite_key},",
            f"  author    = {{{author_str}}},",
            f"  title     = {{{result_title}}},",
        ]
        
        if pub_type == 'inproceedings':
            bibtex_lines.append(f"  booktitle = {{{venue}}},")
        else:
            bibtex_lines.append(f"  journal   = {{{venue}}},")
        
        if year:
            bibtex_lines.append(f"  year      = {{{year}}},")
        
        # 添加URL（如果有）
        pub_url = result.get('pub_url', '')
        if pub_url:
            bibtex_lines.append(f"  url       = {{{pub_url}}},")
        
        bibtex_lines.append("}")
        
        return '\n'.join(bibtex_lines) + '\n'
        
    except Exception as e:
        print(f"  [Google Scholar] 搜索出错: {e}")
        return None


# ==================== 统一的备选搜索接口 ====================

def fallback_search(title, use_arxiv=True, use_scholar=True):
    """
    备选搜索：依次尝试arxiv和google scholar
    返回BibTeX格式字符串，全部失败返回None
    """
    bibtex = None
    
    # 尝试arxiv
    if use_arxiv:
        print("  [尝试 arxiv]...")
        bibtex = search_arxiv(title)
        if bibtex:
            print("  [arxiv] 找到匹配结果")
            return bibtex
        else:
            print("  [arxiv] 未找到匹配结果")
    
    # 尝试Google Scholar
    if use_scholar:
        print("  [尝试 Google Scholar]...")
        time.sleep(1)  # 避免请求过快
        bibtex = search_google_scholar(title)
        if bibtex:
            print("  [Google Scholar] 找到匹配结果")
            return bibtex
        else:
            print("  [Google Scholar] 未找到匹配结果")
    
    return None


if __name__ == '__main__':
    # 测试
    test_title = "Attention Is All You Need"
    print(f"测试搜索: {test_title}")
    print("-" * 50)
    
    print("\n=== arxiv 搜索 ===")
    result = search_arxiv(test_title)
    if result:
        print(result)
    else:
        print("未找到")
    
    print("\n=== Google Scholar 搜索 ===")
    result = search_google_scholar(test_title)
    if result:
        print(result)
    else:
        print("未找到")

