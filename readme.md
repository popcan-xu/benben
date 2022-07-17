* python 3.10.5

* pip install django
    >django 4.0.5

* pip install djangorestframework
    >Successfully installed djangorestframework-3.13.1 pytz-2022.1

* pip install xlrd
    >Successfully installed xlrd-2.0.1，注：xlrd版本只能是1.2.0,升级到2.0.1后无法支持xlsm文件

* pip install requests
    >Successfully installed certifi-2022.6.15 charset-normalizer-2.0.12 idna-3.3 requests-2.28.0 urllib3-1.26.9

* pip install beautifulsoup4
    >Successfully installed beautifulsoup4-4.11.1 soupsieve-2.3.2.post1

---
* urls.py
    ```
    # django3
    from django.conf.urls import url
    # django4
    from django.urls import re_path as url
    ```
