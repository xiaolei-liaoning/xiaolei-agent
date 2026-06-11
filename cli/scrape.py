"""CLI爬虫模块"""

from cli.colors import print_header, print_error, print_success, print_info


async def handle_scrape(args):
    """处理爬虫命令"""
    print_header(f"数据爬取 - {args.site}")

    site = args.site
    action = args.action or "热搜top10"

    print_info(f"站点: {site}")
    print_info(f"动作: {action}")

    try:
        from mcp._impl.web_scraper.handler import scraper_dispatcher

        result = scraper_dispatcher.execute(site_name=site, action=action)

        if result.get("success"):
            print_success("爬取完成")
            if result.get("csv_path"):
                print(f"  CSV: {result['csv_path']}")
            if result.get("md_path"):
                print(f"  报告: {result['md_path']}")
        else:
            print_error(result.get("error", "爬取失败"))

    except Exception as e:
        print_error(f"爬取失败: {e}")


async def handle_scrape_list(args):
    """列出支持的爬虫站点"""
    print_header("支持的爬虫站点")

    try:
        from mcp._impl.web_scraper.handler import scraper_dispatcher, _SITE_ALIASES

        sites = list(_SITE_ALIASES.keys())

        print_info(f"共 {len(sites)} 个站点支持:")
        for site in sites:
            print(f"  • {site}")

    except Exception as e:
        print_error(f"获取站点列表失败: {e}")
