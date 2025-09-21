from typing import List, Optional, Any
from pathlib import Path

import jieba

from app.log import logger
from app.core.config import settings
from app.db import DbOper
from app.db.models.transferhistory import TransferHistory
from app.db.transferhistory_oper import TransferHistoryOper
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.plugindata_oper import PluginDataOper
from app.helper.downloader import DownloaderHelper

from ..core.plunins import PluginChian
from ..utils.path import PathUtils, PathRemoveUtils


class TransferHBOper(DbOper):
    """
    历史记录数据库操作扩展
    """

    def get_transfer_his_by_path_title(self, path: str) -> List[TransferHistory]:
        """
        通过路径查询转移记录
        所有匹配项
        """
        words = jieba.cut(path, HMM=False)
        title = "%".join(words)
        total = TransferHistory.count_by_title(self._db, title=title)
        result = TransferHistory.list_by_title(
            self._db, title=title, page=1, count=total
        )
        return result


class MediaSyncDelHelper:
    """
    媒体文件同步删除

    感谢：
      - https://github.com/thsrite/MoviePilot-Plugins/tree/main/plugins.v2/mediasyncdel
        - LICENSE: https://github.com/thsrite/MoviePilot-Plugins/blob/main/LICENSE
    """

    def __init__(self):
        self.plugindata = PluginDataOper()
        self.downloadhis = DownloadHistoryOper()
        self.transferhis = TransferHistoryOper()
        self.transferhisb = TransferHBOper()
        self.downloader_helper = DownloaderHelper()
        self.chain = PluginChian()

        downloader_services = self.downloader_helper.get_services()
        for downloader_name, downloader_info in downloader_services.items():
            if downloader_info.config.default:
                self.default_downloader = downloader_name

    def get_data(
        self, key: Optional[str] = None, plugin_id: Optional[str] = None
    ) -> Any:
        """
        获取插件数据
        :param key: 数据key
        :param plugin_id: plugin_id
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__
        return self.plugindata.get_data(plugin_id, key)

    def del_data(self, key: str, plugin_id: Optional[str] = None) -> Any:
        """
        删除插件数据
        :param key: 数据key
        :param plugin_id: plugin_id
        """
        if not plugin_id:
            plugin_id = self.__class__.__name__
        return self.plugindata.del_data(plugin_id, key)

    def remove_by_path(self, path: str, del_source: bool = False):
        """
        通过路径删除历史记录和源文件
        """
        transfer_history = self.transferhisb.get_transfer_his_by_path_title(path)

        if not transfer_history:
            logger.warn(f"【同步删除】无 {path} 有关的历史记录")
            return [], [], 0, []

        del_torrent_hashs = []
        stop_torrent_hashs = []
        error_cnt = 0
        for transferhis in transfer_history:
            dest_path = transferhis.dest

            if not PathUtils.has_prefix(dest_path, path):
                logger.warn(f"【同步删除】{dest_path} 不在 {path} 下，跳过删除")
                continue

            self.transferhis.delete(transferhis.id)
            logger.info(f"【同步删除】{transferhis.id} {dest_path} 历史记录已删除")

            if del_source:
                if (
                    transferhis.src
                    and Path(transferhis.src).suffix in settings.RMT_MEDIAEXT
                    and transferhis.src_storage == "local"
                    and transferhis.mode != "move"
                ):
                    if Path(transferhis.src).exists():
                        logger.info(f"【同步删除】源文件 {transferhis.src} 开始删除")
                        Path(transferhis.src).unlink(missing_ok=True)
                        logger.info(f"【同步删除】源文件 {transferhis.src} 已删除")
                        PathRemoveUtils.remove_parent_dir(
                            file_path=Path(transferhis.src),
                            mode=settings.RMT_MEDIAEXT,
                            func_type="【同步删除】"
                        )

                    if transferhis.download_hash:
                        try:
                            # 2、判断种子是否被删除完
                            delete_flag, success_flag, handle_torrent_hashs = (
                                self.handle_torrent(
                                    type=transferhis.type,
                                    src=transferhis.src,
                                    torrent_hash=transferhis.download_hash,
                                )
                            )
                            if not success_flag:
                                error_cnt += 1
                            else:
                                if delete_flag:
                                    del_torrent_hashs += handle_torrent_hashs
                                else:
                                    stop_torrent_hashs += handle_torrent_hashs
                        except Exception as e:
                            logger.error("【同步删除】删除种子失败：%s" % str(e))

        return del_torrent_hashs, stop_torrent_hashs, error_cnt, transfer_history

    def handle_torrent(self, type: str, src: str, torrent_hash: str):
        """
        判断种子是否局部删除
        局部删除则暂停种子
        全部删除则删除种子
        """
        download_id = torrent_hash
        download = self.default_downloader
        history_key = f"{download}-{torrent_hash}"
        plugin_id = "TorrentTransfer"
        transfer_history = self.get_data(key=history_key, plugin_id=plugin_id)
        logger.info(f"【同步删除】查询到 {history_key} 转种历史 {transfer_history}")

        handle_torrent_hashs = []
        try:
            # 删除本次种子记录
            self.downloadhis.delete_file_by_fullpath(fullpath=src)

            # 根据种子hash查询所有下载器文件记录
            download_files = self.downloadhis.get_files_by_hash(
                download_hash=torrent_hash
            )
            if not download_files:
                logger.error(
                    f"【同步删除】未查询到种子任务 {torrent_hash} 存在文件记录，未执行下载器文件同步或该种子已被删除"
                )
                return False, False, []

            # 查询未删除数
            no_del_cnt = 0
            for download_file in download_files:
                if (
                    download_file
                    and download_file.state
                    and int(download_file.state) == 1
                ):
                    no_del_cnt += 1

            if no_del_cnt > 0:
                logger.info(
                    f"【同步删除】查询种子任务 {torrent_hash} 存在 {no_del_cnt} 个未删除文件，执行暂停种子操作"
                )
                delete_flag = False
            else:
                logger.info(
                    f"【同步删除】查询种子任务 {torrent_hash} 文件已全部删除，执行删除种子操作"
                )
                delete_flag = True

            # 如果有转种记录，则删除转种后的下载任务
            if transfer_history and isinstance(transfer_history, dict):
                download = transfer_history["to_download"]
                download_id = transfer_history["to_download_id"]
                delete_source = transfer_history["delete_source"]

                # 删除种子
                if delete_flag:
                    # 删除转种记录
                    self.del_data(key=history_key, plugin_id=plugin_id)

                    # 转种后未删除源种时，同步删除源种
                    if not delete_source:
                        logger.info(
                            f"【同步删除】{history_key} 转种时未删除源下载任务，开始删除源下载任务…"
                        )

                        # 删除源种子
                        logger.info(
                            f"【同步删除】删除源下载器下载任务：{self.default_downloader} - {torrent_hash}"
                        )
                        self.chain.remove_torrents(torrent_hash)
                        handle_torrent_hashs.append(torrent_hash)

                    # 删除转种后任务
                    logger.info(
                        f"【同步删除】删除转种后下载任务：{download} - {download_id}"
                    )
                    # 删除转种后下载任务
                    self.chain.remove_torrents(hashs=torrent_hash, downloader=download)
                    handle_torrent_hashs.append(download_id)
                else:
                    # 暂停种子
                    # 转种后未删除源种时，同步暂停源种
                    if not delete_source:
                        logger.info(
                            f"【同步删除】{history_key} 转种时未删除源下载任务，开始暂停源下载任务…"
                        )

                        # 暂停源种子
                        logger.info(
                            f"【同步删除】暂停源下载器下载任务：{self.default_downloader} - {torrent_hash}"
                        )
                        self.chain.stop_torrents(torrent_hash)
                        handle_torrent_hashs.append(torrent_hash)

                    logger.info(
                        f"【同步删除】暂停转种后下载任务：{download} - {download_id}"
                    )
                    # 删除转种后下载任务
                    self.chain.stop_torrents(hashs=download_id, downloader=download)
                    handle_torrent_hashs.append(download_id)
            else:
                # 未转种的情况
                if delete_flag:
                    # 删除源种子
                    logger.info(
                        f"【同步删除】删除源下载器下载任务：{download} - {download_id}"
                    )
                    self.chain.remove_torrents(download_id)
                else:
                    # 暂停源种子
                    logger.info(
                        f"【同步删除】暂停源下载器下载任务：{download} - {download_id}"
                    )
                    self.chain.stop_torrents(download_id)
                handle_torrent_hashs.append(download_id)

            # 处理辅种
            handle_torrent_hashs = self.__del_seed(
                download_id=download_id,
                delete_flag=delete_flag,
                handle_torrent_hashs=handle_torrent_hashs,
            )
            # 处理合集
            if str(type) == "电视剧":
                handle_torrent_hashs = self.__del_collection(
                    src=src,
                    delete_flag=delete_flag,
                    torrent_hash=torrent_hash,
                    download_files=download_files,
                    handle_torrent_hashs=handle_torrent_hashs,
                )
            return delete_flag, True, handle_torrent_hashs
        except Exception as e:
            logger.error(f"【同步删除】删种失败： {str(e)}")
            return False, False, []

    def __del_collection(
        self,
        src: str,
        delete_flag: bool,
        torrent_hash: str,
        download_files: list,
        handle_torrent_hashs: list,
    ):
        """
        处理做种合集
        """
        try:
            src_download_files = self.downloadhis.get_files_by_fullpath(fullpath=src)
            if src_download_files:
                for download_file in src_download_files:
                    # src查询记录 判断download_hash是否不一致
                    if (
                        download_file
                        and download_file.download_hash
                        and str(download_file.download_hash) != str(torrent_hash)
                    ):
                        # 查询新download_hash对应files数量
                        hash_download_files = self.downloadhis.get_files_by_hash(
                            download_hash=download_file.download_hash
                        )
                        # 新download_hash对应files数量 > 删种download_hash对应files数量 = 合集种子
                        if (
                            hash_download_files
                            and len(hash_download_files) > len(download_files)
                            and hash_download_files[0].id > download_files[-1].id
                        ):
                            # 查询未删除数
                            no_del_cnt = 0
                            for hash_download_file in hash_download_files:
                                if (
                                    hash_download_file
                                    and hash_download_file.state
                                    and int(hash_download_file.state) == 1
                                ):
                                    no_del_cnt += 1
                            if no_del_cnt > 0:
                                logger.info(
                                    f"【同步删除】合集种子 {download_file.download_hash} 文件未完全删除，执行暂停种子操作"
                                )
                                delete_flag = False

                            # 删除合集种子
                            if delete_flag:
                                self.chain.remove_torrents(
                                    hashs=download_file.download_hash,
                                    downloader=download_file.downloader,
                                )
                                logger.info(
                                    f"【同步删除】删除合集种子 {download_file.downloader} {download_file.download_hash}"
                                )
                            else:
                                # 暂停合集种子
                                self.chain.stop_torrents(
                                    hashs=download_file.download_hash,
                                    downloader=download_file.downloader,
                                )
                                logger.info(
                                    f"【同步删除】暂停合集种子 {download_file.downloader} {download_file.download_hash}"
                                )
                            # 已处理种子+1
                            handle_torrent_hashs.append(download_file.download_hash)

                            # 处理合集辅种
                            handle_torrent_hashs = self.__del_seed(
                                download_id=download_file.download_hash,
                                delete_flag=delete_flag,
                                handle_torrent_hashs=handle_torrent_hashs,
                            )
        except Exception as e:
            logger.error(f"【同步删除】处理 {torrent_hash} 合集失败: {e}")

        return handle_torrent_hashs

    def __del_seed(self, download_id, delete_flag, handle_torrent_hashs):
        """
        删除辅种
        """
        # 查询是否有辅种记录
        history_key = download_id
        plugin_id = "IYUUAutoSeed"
        seed_history = self.get_data(key=history_key, plugin_id=plugin_id) or []
        logger.info(f"【同步删除】查询到 {history_key} 辅种历史 {seed_history}")

        # 有辅种记录则处理辅种
        if seed_history and isinstance(seed_history, list):
            for history in seed_history:
                downloader = history.get("downloader")
                torrents = history.get("torrents")
                if not downloader or not torrents:
                    return
                if not isinstance(torrents, list):
                    torrents = [torrents]

                # 删除辅种历史
                for torrent in torrents:
                    handle_torrent_hashs.append(torrent)
                    # 删除辅种
                    if delete_flag:
                        logger.info(f"【同步删除】删除辅种：{downloader} - {torrent}")
                        self.chain.remove_torrents(hashs=torrent, downloader=downloader)
                    # 暂停辅种
                    else:
                        self.chain.stop_torrents(hashs=torrent, downloader=downloader)
                        logger.info(f"【同步删除】辅种：{downloader} - {torrent} 暂停")

                    # 处理辅种的辅种
                    handle_torrent_hashs = self.__del_seed(
                        download_id=torrent,
                        delete_flag=delete_flag,
                        handle_torrent_hashs=handle_torrent_hashs,
                    )

            # 删除辅种历史
            if delete_flag:
                self.del_data(key=history_key, plugin_id=plugin_id)
        return handle_torrent_hashs
