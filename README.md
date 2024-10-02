# puppy
只为辅种，没有其他功能
- 基于Reseed-Puppy修改的自动辅种带WEBUI界面
- 支持所有api/pieces-hash返回405状态的站点
- 支持客户端: qbittorrent,transmission,deluge
- qbittorrent需要4.5以上的才支持远程辅种，不然就需要映射种子文件夹到torrents
# 部署方式
1. Docker运行
    ```bash
    docker run -d --name=puppy --restart=always -p 4532:4532 -e USERNAME=xxxx -e PASSWORD=xxxx kufei/puppy:latest
    ```
- 修改用户名变量USERNAME
- 修改密码变量PASSWORD
