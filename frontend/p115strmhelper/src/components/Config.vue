<template>
  <div class="plugin-config">
    <v-card flat class="rounded border" style="display: flex; flex-direction: column; max-height: 85vh;">
      <!-- 标题区域 -->
      <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-1 bg-primary-lighten-5">
        <v-icon icon="mdi-cog" class="mr-2" color="primary" size="small" />
        <span>115网盘STRM助手配置</span>
      </v-card-title>

      <!-- 通知区域 -->
      <v-card-text class="px-3 py-2" style="flex-grow: 1; overflow-y: auto; padding-bottom: 56px;">
        <v-alert v-if="message.text" :type="message.type" density="compact" class="mb-2 text-caption" variant="tonal"
          closable>{{ message.text }}</v-alert>

        <v-skeleton-loader v-if="loading" type="article, actions"></v-skeleton-loader>

        <div v-else class="my-1">
          <!-- 基础设置 -->
          <v-card flat class="rounded mb-3 border config-card">
            <v-card-title class="text-subtitle-2 d-flex align-center px-3 py-1 bg-primary-lighten-5">
              <v-icon icon="mdi-cog" class="mr-2" color="primary" size="small" />
              <span>基础设置</span>
            </v-card-title>
            <v-card-text class="pa-3">
              <v-row>
                <v-col cols="12" md="4">
                  <v-switch v-model="config.enabled" label="启用插件" color="success" density="compact"></v-switch>
                </v-col>
                <v-col cols="12" md="4">
                  <v-select v-model="config.strm_url_format" label="STRM文件URL格式" :items="[
                    { title: 'pickcode', value: 'pickcode' },
                    { title: 'pickcode + name', value: 'pickname' }
                  ]" chips closable-chips></v-select>
                </v-col>
                <v-col cols="12" md="4">
                  <v-select v-model="config.link_redirect_mode" label="直链获取模式" :items="[
                    { title: 'Cookie', value: 'cookie' },
                    { title: 'OpenAPI', value: 'open' }
                  ]" chips closable-chips></v-select>
                </v-col>
              </v-row>
              <v-row>
                <v-col cols="12" md="4">
                  <v-switch v-model="config.notify" label="发送通知" color="success" density="compact"></v-switch>
                </v-col>
                <v-col cols="12" md="8">
                  <v-select v-model="config.language" label="通知语言" :items="[
                    { title: '简体中文', value: 'zh_CN' },
                    { title: '繁中台湾', value: 'zh_TW' },
                    { title: '繁中港澳', value: 'zh_HK' },
                    { title: '柔情猫娘', value: 'zh_CN_catgirl' },
                    { title: '粤韵风华', value: 'zh_yue' },
                    { title: '咚咚搬砖', value: 'zh_CN_dong' }
                  ]" chips closable-chips></v-select>
                </v-col>
              </v-row>
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field v-model="config.cookies" label="115 Cookie" hint="点击图标切换显隐、复制或扫码" persistent-hint
                    density="compact" variant="outlined" hide-details="auto"
                    :type="isCookieVisible ? 'text' : 'password'">
                    <template v-slot:append-inner>
                      <v-icon :icon="isCookieVisible ? 'mdi-eye-off' : 'mdi-eye'"
                        @click="isCookieVisible = !isCookieVisible"
                        :aria-label="isCookieVisible ? '隐藏Cookie' : '显示Cookie'"
                        :title="isCookieVisible ? '隐藏Cookie' : '显示Cookie'" class="mr-1" size="small"></v-icon>
                      <v-icon icon="mdi-content-copy" @click="copyCookieToClipboard" :disabled="!config.cookies"
                        aria-label="复制Cookie" title="复制Cookie到剪贴板" size="small" class="mr-1"></v-icon>
                    </template>
                    <template v-slot:append>
                      <v-icon icon="mdi-qrcode-scan" @click="openQrCodeDialog"
                        :color="config.cookies ? 'success' : 'default'"
                        :aria-label="config.cookies ? '更新/更换Cookie (重新扫码)' : '扫码获取Cookie'"
                        :title="config.cookies ? '更新/更换Cookie (重新扫码)' : '扫码获取Cookie'"></v-icon>
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field v-model="config.moviepilot_address" label="MoviePilot 内网访问地址" hint="点右侧图标自动填充当前站点地址。"
                    persistent-hint density="compact" variant="outlined" hide-details="auto">
                    <template v-slot:append>
                      <v-icon icon="mdi-web" @click="setMoviePilotAddressToCurrentOrigin" aria-label="使用当前站点地址"
                        title="使用当前站点地址" color="info"></v-icon>
                    </template>
                  </v-text-field>
                </v-col>
              </v-row>
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field v-model="config.user_rmt_mediaext" label="可整理媒体文件扩展名" hint="支持的媒体文件扩展名，多个用逗号分隔"
                    persistent-hint density="compact" variant="outlined" hide-details="auto"></v-text-field>
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field v-model="config.user_download_mediaext" label="可下载媒体数据文件扩展名"
                    hint="下载的字幕等附属文件扩展名，多个用逗号分隔" persistent-hint density="compact" variant="outlined"
                    hide-details="auto"></v-text-field>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- 标签页 -->
          <v-card flat class="rounded mb-3 border config-card">
            <v-tabs v-model="activeTab" color="primary" bg-color="grey-lighten-3" class="rounded-t" grow>
              <v-tab value="tab-transfer" class="text-caption">
                <v-icon size="small" start>mdi-file-move-outline</v-icon>监控MP整理
              </v-tab>
              <v-tab value="tab-sync" class="text-caption">
                <v-icon size="small" start>mdi-sync</v-icon>全量同步
              </v-tab>
              <v-tab value="tab-increment-sync" class="text-caption">
                <v-icon size="small" start>mdi-book-sync</v-icon>增量同步
              </v-tab>
              <v-tab value="tab-life" class="text-caption">
                <v-icon size="small" start>mdi-calendar-heart</v-icon>监控115生活事件
              </v-tab>
              <v-tab value="tab-cleanup" class="text-caption">
                <v-icon size="small" start>mdi-broom</v-icon>定期清理
              </v-tab>
              <v-tab value="tab-pan-transfer" class="text-caption">
                <v-icon size="small" start>mdi-transfer</v-icon>网盘整理
              </v-tab>
              <v-tab value="tab-directory-upload" class="text-caption">
                <v-icon size="small" start>mdi-upload</v-icon>目录上传
              </v-tab>
              <v-tab value="tab-tg-search" class="text-caption">
                <v-icon size="small" start>mdi-tab-search</v-icon>频道搜索
              </v-tab>
              <v-tab value="tab-same-playback" class="text-caption">
                <v-icon size="small" start>mdi:code-block-parentheses</v-icon>多端播放
              </v-tab>
            </v-tabs>
            <v-divider></v-divider>

            <v-window v-model="activeTab">
              <!-- 监控MP整理 -->
              <v-window-item value="tab-transfer">
                <v-card-text>
                  <v-row>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.transfer_monitor_enabled" label="启用" color="info"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.transfer_monitor_scrape_metadata_enabled" label="STRM自动刮削"
                        color="primary"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.transfer_monitor_media_server_refresh_enabled" label="媒体服务器刷新"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-select v-model="config.transfer_monitor_mediaservers" label="媒体服务器" :items="mediaservers"
                        multiple chips closable-chips></v-select>
                    </v-col>
                  </v-row>

                  <!-- Transfer Monitor Exclude Paths -->
                  <v-row v-if="config.transfer_monitor_scrape_metadata_enabled" class="mt-2 mb-2">
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(item, index) in transferExcludePaths" :key="`transfer-exclude-${index}`"
                          class="mb-2 d-flex align-center">
                          <v-text-field v-model="item.path" label="刮削排除目录" density="compact" variant="outlined" readonly
                            hide-details class="flex-grow-1 mr-2">
                          </v-text-field>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removeExcludePathEntry(index, 'transfer_exclude')" :disabled="!item.path">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-folder-plus-outline" variant="tonal"
                          class="mt-1 align-self-start"
                          @click="openExcludeDirSelector('transfer_monitor_scrape_metadata_exclude_paths')">
                          添加刮削排除目录
                        </v-btn>
                      </div>
                      <v-alert density="compact" variant="text" color="info" class="text-caption pa-0 mt-1">
                        此处添加的本地目录，在STRM文件生成后将不会自动触发刮削。
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in transferPaths" :key="`transfer-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="本地STRM目录" density="compact"
                              append-icon="mdi-folder"
                              @click:append="openDirSelector(index, 'local', 'transfer')"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="网盘媒体库目录" density="compact"
                              append-icon="mdi-folder-network"
                              @click:append="openDirSelector(index, 'remote', 'transfer')"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2" @click="removePath(index, 'transfer')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('transfer')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        监控MoviePilot整理入库事件，自动在本地对应目录生成STRM文件。<br>
                        本地STRM目录：本地STRM文件生成路径
                        网盘媒体库目录：需要生成本地STRM文件的网盘媒体库路径
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in transferMpPaths" :key="`mp-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="媒体库服务器映射目录" density="compact"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="MP映射目录" density="compact"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2" @click="removePath(index, 'mp')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('mp')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        媒体服务器映射路径和MP映射路径不一样时请配置此项，如果不配置则无法正常刷新。<br>
                        当映射路径一样时可省略此配置。
                      </v-alert>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-window-item>

              <!-- 全量同步 -->
              <v-window-item value="tab-sync">
                <v-card-text>
                  <!-- 基础配置 -->
                  <div class="basic-config">
                    <v-row>
                      <v-col cols="12" md="4">
                        <v-select v-model="config.full_sync_overwrite_mode" label="覆盖模式" :items="[
                          { title: '总是', value: 'always' },
                          { title: '从不', value: 'never' }
                        ]" chips closable-chips></v-select>
                      </v-col>
                      <v-col cols="12" md="4">
                        <v-switch v-model="config.full_sync_remove_unless_strm" label="清理失效STRM文件"
                          color="warning"></v-switch>
                      </v-col>
                      <v-col cols="12" md="4">
                        <v-switch v-model="config.full_sync_auto_download_mediainfo_enabled" label="下载媒体数据文件"
                          color="warning"></v-switch>
                      </v-col>
                    </v-row>

                    <v-row>
                      <v-col cols="12" md="6">
                        <v-switch v-model="config.timing_full_sync_strm" label="定期全量同步" color="info"></v-switch>
                      </v-col>
                      <v-col cols="12" md="6">
                        <VCronField v-model="config.cron_full_sync_strm" label="运行全量同步周期" hint="设置全量同步的执行周期"
                          persistent-hint density="compact"></VCronField>
                      </v-col>
                    </v-row>

                    <v-row>
                      <v-col cols="12">
                        <div class="d-flex flex-column">
                          <div v-for="(pair, index) in fullSyncPaths" :key="`full-${index}`"
                            class="mb-2 d-flex align-center">
                            <div class="path-selector flex-grow-1 mr-2">
                              <v-text-field v-model="pair.local" label="本地STRM目录" density="compact"
                                append-icon="mdi-folder"
                                @click:append="openDirSelector(index, 'local', 'fullSync')"></v-text-field>
                            </div>
                            <v-icon>mdi-pound</v-icon>
                            <div class="path-selector flex-grow-1 ml-2">
                              <v-text-field v-model="pair.remote" label="网盘媒体库目录" density="compact"
                                append-icon="mdi-folder-network"
                                @click:append="openDirSelector(index, 'remote', 'fullSync')"></v-text-field>
                            </div>
                            <v-btn icon size="small" color="error" class="ml-2" @click="removePath(index, 'fullSync')">
                              <v-icon>mdi-delete</v-icon>
                            </v-btn>
                          </div>
                          <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                            @click="addPath('fullSync')">
                            添加路径
                          </v-btn>
                        </div>

                        <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                          全量扫描配置的网盘目录，并在对应的本地目录生成STRM文件。<br>
                          本地STRM目录：本地STRM文件生成路径
                          网盘媒体库目录：需要生成本地STRM文件的网盘媒体库路径
                        </v-alert>
                      </v-col>
                    </v-row>
                  </div>

                  <!-- 高级配置 -->
                  <v-expansion-panels variant="tonal" class="mt-6">
                    <v-expansion-panel>
                      <v-expansion-panel-title>
                        <v-icon icon="mdi-tune-variant" class="mr-2"></v-icon>
                        高级配置
                      </v-expansion-panel-title>
                      <v-expansion-panel-text class="pa-4">
                        <v-row>
                          <v-col cols="12" md="3">
                            <v-switch v-model="config.full_sync_strm_log" label="输出STRM同步日志" color="primary"></v-switch>
                          </v-col>
                          <v-col cols="12" md="3">
                            <v-text-field v-model.number="config.full_sync_batch_num" label="全量同步批处理数量" type="number"
                              hint="每次批量处理的文件/目录数量" persistent-hint density="compact"></v-text-field>
                          </v-col>
                          <v-col cols="12" md="3">
                            <v-text-field v-model.number="config.full_sync_process_num" label="全量同步生成进程数" type="number"
                              hint="同时执行同步任务的进程数量" persistent-hint density="compact"></v-text-field>
                          </v-col>
                          <v-col cols="12" md="3">
                            <v-select v-model="config.full_sync_iter_function" label="迭代函数" :items="[
                              { title: 'iter_files_with_path_skim', value: 'iter_files_with_path_skim' },
                              { title: 'iter_files_with_path', value: 'iter_files_with_path' }
                            ]" chips closable-chips></v-select>
                          </v-col>
                        </v-row>
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>

                </v-card-text>
              </v-window-item>

              <!-- 增量 -->
              <v-window-item value="tab-increment-sync">
                <v-card-text>

                  <v-row>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.increment_sync_strm_enabled" label="启用" color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="9">
                      <VCronField v-model="config.increment_sync_cron" label="运行增量同步周期" hint="设置增量同步的执行周期"
                        persistent-hint density="compact"></VCronField>
                    </v-col>
                  </v-row>
                  <v-row>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.increment_sync_auto_download_mediainfo_enabled" label="下载媒体数据文件"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.increment_sync_scrape_metadata_enabled" label="STRM自动刮削"
                        color="primary"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.increment_sync_media_server_refresh_enabled" label="媒体服务器刷新"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-select v-model="config.increment_sync_mediaservers" label="媒体服务器" :items="mediaservers"
                        multiple chips closable-chips></v-select>
                    </v-col>
                  </v-row>

                  <v-row v-if="config.increment_sync_scrape_metadata_enabled" class="mt-2 mb-2">
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(item, index) in incrementSyncExcludePaths" :key="`increment-exclude-${index}`"
                          class="mb-2 d-flex align-center">
                          <v-text-field v-model="item.path" label="刮削排除目录" density="compact" variant="outlined" readonly
                            hide-details class="flex-grow-1 mr-2">
                          </v-text-field>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removeExcludePathEntry(index, 'increment_exclude')" :disabled="!item.path">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-folder-plus-outline" variant="tonal"
                          class="mt-1 align-self-start"
                          @click="openExcludeDirSelector('increment_sync_scrape_metadata_exclude_paths')">
                          添加刮削排除目录
                        </v-btn>
                      </div>
                      <v-alert density="compact" variant="text" color="info" class="text-caption pa-0 mt-1">
                        此处添加的本地目录，在STRM文件生成后将不会自动触发刮削。
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in incrementSyncPaths" :key="`increment-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="本地STRM目录" density="compact"
                              append-icon="mdi-folder"
                              @click:append="openDirSelector(index, 'local', 'incrementSync')"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="网盘媒体库目录" density="compact"
                              append-icon="mdi-folder-network"
                              @click:append="openDirSelector(index, 'remote', 'incrementSync')"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removePath(index, 'incrementSync')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('incrementSync')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        增量扫描配置的网盘目录，并在对应的本地目录生成STRM文件。<br>
                        本地STRM目录：本地STRM文件生成路径
                        网盘媒体库目录：需要生成本地STRM文件的网盘媒体库路径
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in incrementSyncMPPaths" :key="`increment-mp-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="媒体库服务器映射目录" density="compact"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="MP映射目录" density="compact"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removePath(index, 'increment-mp')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('increment-mp')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        媒体服务器映射路径和MP映射路径不一样时请配置此项，如果不配置则无法正常刷新。<br>
                        当映射路径一样时可省略此配置。
                      </v-alert>
                    </v-col>
                  </v-row>

                </v-card-text>
              </v-window-item>

              <!-- 监控115生活事件 -->
              <v-window-item value="tab-life">
                <v-card-text>
                  <v-row>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.monitor_life_enabled" label="启用" color="info"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-select v-model="config.monitor_life_event_modes" label="处理事件类型" :items="[
                        { title: '新增事件', value: 'creata' },
                        { title: '删除事件', value: 'remove' },
                        { title: '网盘整理', value: 'transfer' }
                      ]" multiple chips closable-chips></v-select>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.monitor_life_auto_download_mediainfo_enabled" label="下载媒体数据文件"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.monitor_life_scrape_metadata_enabled" label="STRM自动刮削"
                        color="primary"></v-switch>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.monitor_life_media_server_refresh_enabled" label="媒体服务器刷新"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="8">
                      <v-select v-model="config.monitor_life_mediaservers" label="媒体服务器" :items="mediaservers" multiple
                        chips closable-chips></v-select>
                    </v-col>
                  </v-row>

                  <!-- Monitor Life Exclude Paths -->
                  <v-row v-if="config.monitor_life_scrape_metadata_enabled" class="mt-2 mb-2">
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(item, index) in monitorLifeExcludePaths" :key="`life-exclude-${index}`"
                          class="mb-2 d-flex align-center">
                          <v-text-field v-model="item.path" label="刮削排除目录" density="compact" variant="outlined" readonly
                            hide-details class="flex-grow-1 mr-2">
                          </v-text-field>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removeExcludePathEntry(index, 'life_exclude')" :disabled="!item.path">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-folder-plus-outline" variant="tonal"
                          class="mt-1 align-self-start"
                          @click="openExcludeDirSelector('monitor_life_scrape_metadata_exclude_paths')">
                          添加刮削排除目录
                        </v-btn>
                      </div>
                      <v-alert density="compact" variant="text" color="info" class="text-caption pa-0 mt-1">
                        此处添加的本地目录，在115生活事件监控生成STRM后将不会自动触发刮削。
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in monitorLifePaths" :key="`life-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="本地STRM目录" density="compact"
                              append-icon="mdi-folder"
                              @click:append="openDirSelector(index, 'local', 'monitorLife')"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="网盘媒体库目录" density="compact"
                              append-icon="mdi-folder-network"
                              @click:append="openDirSelector(index, 'remote', 'monitorLife')"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2" @click="removePath(index, 'monitorLife')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('monitorLife')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        监控115生活（上传、移动、接收文件、删除、复制）事件，自动在本地对应目录生成STRM文件或者删除STRM文件。<br>
                        本地STRM目录：本地STRM文件生成路径
                        网盘媒体库目录：需要生成本地STRM文件的网盘媒体库路径
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(pair, index) in monitorLifeMpPaths" :key="`life-mp-${index}`"
                          class="mb-2 d-flex align-center">
                          <div class="path-selector flex-grow-1 mr-2">
                            <v-text-field v-model="pair.local" label="媒体库服务器映射目录" density="compact"></v-text-field>
                          </div>
                          <v-icon>mdi-pound</v-icon>
                          <div class="path-selector flex-grow-1 ml-2">
                            <v-text-field v-model="pair.remote" label="MP映射目录" density="compact"></v-text-field>
                          </div>
                          <v-btn icon size="small" color="error" class="ml-2"
                            @click="removePath(index, 'monitorLifeMp')">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPath('monitorLifeMp')">
                          添加路径
                        </v-btn>
                      </div>

                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        媒体服务器映射路径和MP映射路径不一样时请配置此项，如果不配置则无法正常刷新。<br>
                        当映射路径一样时可省略此配置。
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-alert type="warning" variant="tonal" density="compact" class="mt-2">
                    注意：当 MoviePilot 主程序运行整理任务时 115生活事件 监控会自动暂停，整理运行完成后会继续监控。
                  </v-alert>
                </v-card-text>
              </v-window-item>

              <!-- 定期清理 -->
              <v-window-item value="tab-cleanup">
                <v-card-text>
                  <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
                    注意，清空 回收站/最近接收 后文件不可恢复，如果产生重要数据丢失本程序不负责！
                  </v-alert>

                  <v-row>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.clear_recyclebin_enabled" label="清空回收站" color="error"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.clear_receive_path_enabled" label="清空最近接收目录" color="error"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-text-field v-model="config.password" label="115访问密码" hint="115网盘登录密码" persistent-hint
                        type="password" density="compact" variant="outlined" hide-details="auto"></v-text-field>
                    </v-col>
                    <v-col cols="12" md="3">
                      <VCronField v-model="config.cron_clear" label="清理周期" hint="设置清理任务的执行周期" persistent-hint
                        density="compact">
                      </VCronField>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-window-item>

              <!-- 网盘整理 -->
              <v-window-item value="tab-pan-transfer">
                <v-card-text>
                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.pan_transfer_enabled" label="启用" color="info"></v-switch>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12">
                      <div class="d-flex flex-column">
                        <div v-for="(path, index) in panTransferPaths" :key="`pan-${index}`"
                          class="mb-2 d-flex align-center">
                          <v-text-field v-model="path.path" label="网盘待整理目录" density="compact"
                            append-icon="mdi-folder-network"
                            @click:append="openDirSelector(index, 'remote', 'panTransfer')"
                            class="flex-grow-1"></v-text-field>
                          <v-btn icon size="small" color="error" class="ml-2" @click="removePanTransferPath(index)">
                            <v-icon>mdi-delete</v-icon>
                          </v-btn>
                        </div>
                        <v-btn size="small" prepend-icon="mdi-plus" variant="outlined" class="mt-2 align-self-start"
                          @click="addPanTransferPath">
                          添加路径
                        </v-btn>
                      </div>
                    </v-col>
                  </v-row>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                    使用本功能需要先进入 设定-目录 进行配置：<br>
                    1. 添加目录配置卡，按需配置媒体类型和媒体类别，资源存储选择115网盘，资源目录输入网盘待整理文件夹<br>
                    2. 自动整理模式选择手动整理，媒体库存储依旧选择115网盘，并配置好媒体库路径，整理方式选择移动，按需配置分类、重命名、通知<br>
                    3. 配置完成目录设置后只需要在上方 网盘待整理目录 填入 网盘待整理文件夹 即可<br>
                  </v-alert>

                  <v-alert type="warning" variant="tonal" density="compact" class="mt-2">
                    注意：配置目录时不能选择刮削元数据，否则可能导致风控！
                  </v-alert>

                  <v-alert type="warning" variant="tonal" density="compact" class="mt-2">
                    注意：115生活事件监控默认会忽略网盘整理触发的移动事件，所以推荐使用MP整理事件监控生成STRM
                  </v-alert>
                </v-card-text>
              </v-window-item>

              <!-- 目录上传 -->
              <v-window-item value="tab-directory-upload">
                <v-card-text>
                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.directory_upload_enabled" label="启用" color="info" density="compact"
                        hide-details></v-switch>
                    </v-col>
                    <v-col cols="12" md="8">
                      <v-select v-model="config.directory_upload_mode" label="监控模式" :items="[
                        { title: '兼容模式', value: 'compatibility' },
                        { title: '性能模式', value: 'fast' }
                      ]" chips closable-chips density="compact" hide-details></v-select>
                    </v-col>
                  </v-row>
                  <v-row>
                    <v-col cols="12" md="6">
                      <v-text-field v-model="config.directory_upload_uploadext" label="上传文件扩展名"
                        hint="指定哪些扩展名的文件会被上传到115网盘，多个用逗号分隔" persistent-hint density="compact" variant="outlined"
                        hide-details="auto"></v-text-field>
                    </v-col>
                    <v-col cols="12" md="6">
                      <v-text-field v-model="config.directory_upload_copyext" label="复制文件扩展名"
                        hint="指定哪些扩展名的文件会被复制到本地目标目录，多个用逗号分隔" persistent-hint density="compact" variant="outlined"
                        hide-details="auto"></v-text-field>
                    </v-col>
                  </v-row>

                  <v-divider class="my-3"></v-divider>
                  <div class="text-subtitle-2 mb-2">路径配置:</div>

                  <div v-for="(pair, index) in directoryUploadPaths" :key="`upload-${index}`"
                    class="path-group mb-3 pa-2 border rounded">
                    <v-row dense>
                      <!-- 本地监控目录 -->
                      <v-col cols="12" md="6">
                        <v-text-field v-model="pair.src" label="本地监控目录" density="compact" variant="outlined"
                          hide-details append-icon="mdi-folder-search-outline"
                          @click:append="openDirSelector(index, 'local', 'directoryUpload', 'src')">
                          <template v-slot:prepend-inner>
                            <v-icon color="blue">mdi-folder-table</v-icon>
                          </template>
                        </v-text-field>
                      </v-col>
                      <!-- 网盘上传目录 -->
                      <v-col cols="12" md="6">
                        <v-text-field v-model="pair.dest_remote" label="网盘上传目标目录" density="compact" variant="outlined"
                          hide-details append-icon="mdi-folder-network-outline"
                          @click:append="openDirSelector(index, 'remote', 'directoryUpload', 'dest_remote')">
                          <template v-slot:prepend-inner>
                            <v-icon color="green">mdi-cloud-upload</v-icon>
                          </template>
                        </v-text-field>
                      </v-col>
                    </v-row>
                    <v-row dense class="mt-1">
                      <!-- 非上传文件目标目录 -->
                      <v-col cols="12" md="6">
                        <v-text-field v-model="pair.dest_local" label="本地复制目标目录 (可选)" density="compact"
                          variant="outlined" hide-details append-icon="mdi-folder-plus-outline"
                          @click:append="openDirSelector(index, 'local', 'directoryUpload', 'dest_local')">
                          <template v-slot:prepend-inner>
                            <v-icon color="orange">mdi-content-copy</v-icon>
                          </template>
                        </v-text-field>
                      </v-col>
                      <!-- 删除源文件开关 -->
                      <v-col cols="12" md="4" class="d-flex align-center">
                        <v-switch v-model="pair.delete" label="处理后删除源文件" color="error" density="compact"
                          hide-details></v-switch>
                      </v-col>
                      <!-- 删除按钮 -->
                      <v-col cols="12" md="2" class="d-flex align-center justify-end">
                        <v-btn icon="mdi-delete-outline" size="small" color="error" variant="text" title="删除此路径配置"
                          @click="removePath(index, 'directoryUpload')">
                        </v-btn>
                      </v-col>
                    </v-row>
                  </div>

                  <v-btn size="small" prepend-icon="mdi-plus-box-multiple-outline" variant="tonal" class="mt-2"
                    color="primary" @click="addPath('directoryUpload')">
                    添加监控路径组
                  </v-btn>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
                    <strong>功能说明:</strong><br>
                    - 监控指定的"本地监控目录"。<br>
                    - 当目录中出现新文件时：<br>
                    &nbsp;&nbsp;- 如果文件扩展名匹配"上传文件扩展名"，则将其上传到对应的"网盘上传目标目录"。<br>
                    &nbsp;&nbsp;- 如果文件扩展名匹配"复制文件扩展名"，则将其复制到对应的"本地复制目标目录"。<br>
                    - 处理完成后，如果"删除源文件"开关打开，则会删除原始文件。<br>
                    - 扩展名不匹配的文件将被忽略。<br>
                    <strong>注意:</strong><br>
                    - 请确保MoviePilot对本地目录有读写权限，对网盘目录有写入权限。<br>
                    - "本地复制目标目录"是可选的，如果不填，则仅执行上传操作（如果匹配）。<br>
                    - 监控模式："兼容模式"适用于Docker或网络共享目录（如SMB），性能较低；"性能模式"仅适用于物理路径，性能较高。
                  </v-alert>
                </v-card-text>
              </v-window-item>

              <!-- 频道搜索 -->
              <v-window-item value="tab-tg-search">
                <v-card-text>

                  <v-row>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="config.cloudsaver_url" label="CloudSaver 地址" hint="CloudSaver 地址"
                        persistent-hint density="compact" variant="outlined" hide-details="auto"></v-text-field>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="config.cloudsaver_username" label="CloudSaver 用户名" hint="CloudSaver 用户名"
                        persistent-hint density="compact" variant="outlined" hide-details="auto"></v-text-field>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="config.cloudsaver_password" label="CloudSaver 密码" hint="CloudSaver 密码"
                        persistent-hint type="password" density="compact" variant="outlined"
                        hide-details="auto"></v-text-field>
                    </v-col>
                  </v-row>

                  <v-row>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="config.nullbr_app_id" label="Nullbr APP ID" hint="Nullbr APP ID"
                        persistent-hint density="compact" variant="outlined" hide-details="auto"></v-text-field>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="config.nullbr_api_key" label="Nullbr API KEY" hint="Nullbr API KEY"
                        persistent-hint density="compact" variant="outlined" hide-details="auto"></v-text-field>
                    </v-col>
                  </v-row>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
                    <strong>Telegram频道搜索功能说明</strong><br><br>

                    <strong>🔧 实现方式</strong><br>
                    本功能通过对接以下两个服务平台实现：<br>
                    1. CloudSaver (<a href="https://github.com/jiangrui1994/CloudSaver"
                      target="_blank">https://github.com/jiangrui1994/CloudSaver</a>)<br>
                    2. Nullbr (<a href="https://nullbr.online/" target="_blank">https://nullbr.online/</a>)<br><br>

                    <strong>⚙️ 配置要求</strong><br>
                    您需要至少完成其中一个平台的配置才能使用搜索功能：<br><br>

                    <strong>CloudSaver配置：</strong><br>
                    - 服务地址<br>
                    - 用户名<br>
                    - 密码<br><br>

                    <strong>Nullbr配置：</strong><br>
                    - 需要从官网申请 APP ID<br>
                    - 需要从官网申请 API Key<br><br>

                    <strong>💡 使用建议</strong><br>
                    - 可以同时配置两个平台<br>
                    - 如果两者都配置，系统会优先显示Nullbr的资源结果<br>
                    - 配置越多，可搜索的资源范围越广
                  </v-alert>
                </v-card-text>
              </v-window-item>

              <!-- 多端播放 -->
              <v-window-item value="tab-same-playback">
                <v-card-text>

                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.same_playback" label="启用" color="info" density="compact"
                        hide-details></v-switch>
                    </v-col>
                  </v-row>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
                    <strong>多设备同步播放</strong><br> •
                    支持多个设备同时播放同一影片
                  </v-alert>
                  <v-alert type="warning" variant="tonal" density="compact" class="mt-2">
                    <strong>使用限制</strong><br> • 最多支持双IP同时播放<br> • 禁止多IP滥用<br> • 违规操作可能导致账号封禁 </v-alert>
                </v-card-text>
              </v-window-item>

            </v-window>
          </v-card>

          <!-- 操作按钮 -->

        </div>
      </v-card-text>
      <v-card-actions class="px-3 py-2 d-flex" style="flex-shrink: 0;">
        <v-btn color="warning" variant="text" @click="emit('switch')" size="small" prepend-icon="mdi-arrow-left">
          返回
        </v-btn>
        <v-spacer></v-spacer>
        <v-btn color="warning" variant="text" @click="fullSyncConfirmDialog = true" size="small"
          prepend-icon="mdi-sync">
          全量同步
        </v-btn>
        <v-btn color="success" variant="text" @click="saveConfig" :loading="saveLoading" size="small"
          prepend-icon="mdi-content-save">
          保存配置
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- 全量同步确认对话框 -->
    <v-dialog v-model="fullSyncConfirmDialog" max-width="450" persistent>
      <v-card>
        <v-card-title class="text-h6 d-flex align-center">
          <v-icon icon="mdi-alert-circle-outline" color="warning" class="mr-2"></v-icon>
          确认操作
        </v-card-title>
        <v-card-text>
          您确定要立即执行全量同步吗？
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="fullSyncConfirmDialog = false" :disabled="syncLoading">
            取消
          </v-btn>
          <v-btn color="warning" variant="text" @click="handleConfirmFullSync" :loading="syncLoading">
            确认执行
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 目录选择器对话框 -->
    <v-dialog v-model="dirDialog.show" max-width="800">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
          <v-icon :icon="dirDialog.isLocal ? 'mdi-folder-search' : 'mdi-folder-network'" class="mr-2" color="primary" />
          <span>{{ dirDialog.isLocal ? '选择本地目录' : '选择网盘目录' }}</span>
        </v-card-title>

        <v-card-text class="px-3 py-2">
          <div v-if="dirDialog.loading" class="d-flex justify-center my-3">
            <v-progress-circular indeterminate color="primary"></v-progress-circular>
          </div>

          <div v-else>
            <!-- 当前路径显示 -->
            <v-text-field v-model="dirDialog.currentPath" label="当前路径" variant="outlined" density="compact" class="mb-2"
              @keyup.enter="loadDirContent"></v-text-field>

            <!-- 文件列表 -->
            <v-list class="border rounded" max-height="300px" overflow-y="auto">
              <v-list-item
                v-if="dirDialog.currentPath !== '/' && dirDialog.currentPath !== 'C:\\' && dirDialog.currentPath !== 'C:/'"
                @click="navigateToParentDir" class="py-1">
                <template v-slot:prepend>
                  <v-icon icon="mdi-arrow-up" size="small" class="mr-2" color="grey" />
                </template>
                <v-list-item-title class="text-body-2">上级目录</v-list-item-title>
                <v-list-item-subtitle>..</v-list-item-subtitle>
              </v-list-item>

              <v-list-item v-for="(item, index) in dirDialog.items" :key="index" @click="selectDir(item)"
                :disabled="!item.is_dir" class="py-1">
                <template v-slot:prepend>
                  <v-icon :icon="item.is_dir ? 'mdi-folder' : 'mdi-file'" size="small" class="mr-2"
                    :color="item.is_dir ? 'amber-darken-2' : 'blue'" />
                </template>
                <v-list-item-title class="text-body-2">{{ item.name }}</v-list-item-title>
              </v-list-item>

              <v-list-item v-if="!dirDialog.items.length" class="py-2 text-center">
                <v-list-item-title class="text-body-2 text-grey">该目录为空或访问受限</v-list-item-title>
              </v-list-item>
            </v-list>
          </div>

          <v-alert v-if="dirDialog.error" type="error" density="compact" class="mt-2 text-caption" variant="tonal">
            {{ dirDialog.error }}
          </v-alert>
        </v-card-text>

        <v-card-actions class="px-3 py-2">
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="confirmDirSelection" :disabled="!dirDialog.currentPath || dirDialog.loading"
            variant="text" size="small">
            选择当前目录
          </v-btn>
          <v-btn color="grey" @click="closeDirDialog" variant="text" size="small">
            取消
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 二维码登录对话框 -->
    <v-dialog v-model="qrDialog.show" max-width="450">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
          <v-icon icon="mdi-qrcode" class="mr-2" color="primary" size="small" />
          <span>115网盘扫码登录</span>
        </v-card-title>

        <v-card-text class="text-center py-4">
          <v-alert v-if="qrDialog.error" type="error" density="compact" class="mb-3 mx-3" variant="tonal" closable>
            {{ qrDialog.error }}
          </v-alert>

          <div v-if="qrDialog.loading" class="d-flex flex-column align-center py-3">
            <v-progress-circular indeterminate color="primary" class="mb-3"></v-progress-circular>
            <div>正在获取二维码...</div>
          </div>

          <div v-else-if="qrDialog.qrcode" class="d-flex flex-column align-center">
            <div class="mb-2 font-weight-medium">请选择扫码方式</div>
            <v-chip-group v-model="qrDialog.clientType" class="mb-3" mandatory selected-class="primary">
              <v-chip v-for="type in clientTypes" :key="type.value" :value="type.value" variant="outlined"
                color="primary" size="small">
                {{ type.label }}
              </v-chip>
            </v-chip-group>
            <div class="d-flex flex-column align-center mb-3">
              <v-card flat class="border pa-2 mb-2">
                <img :src="qrDialog.qrcode" width="220" height="220" />
              </v-card>
              <div class="text-body-2 text-grey mb-1">{{ qrDialog.tips }}</div>
              <div class="text-subtitle-2 font-weight-medium text-primary">{{ qrDialog.status }}</div>
            </div>
            <v-btn color="primary" variant="tonal" @click="refreshQrCode" size="small" class="mb-2">
              <v-icon left size="small" class="mr-1">mdi-refresh</v-icon>刷新二维码
            </v-btn>
          </div>

          <div v-else class="d-flex flex-column align-center py-3">
            <v-icon icon="mdi-qrcode-off" size="64" color="grey" class="mb-3"></v-icon>
            <div class="text-subtitle-1">二维码获取失败</div>
            <div class="text-body-2 text-grey">请点击刷新按钮重试</div>
            <div class="text-caption mt-2 text-grey">
              <v-icon icon="mdi-alert-circle" size="small" class="mr-1 text-warning"></v-icon>
              如果多次获取失败，请检查网络连接
            </div>
          </div>
        </v-card-text>

        <v-divider></v-divider>
        <v-card-actions class="px-3 py-2">
          <v-btn color="grey" variant="text" @click="closeQrDialog" size="small" prepend-icon="mdi-close">关闭</v-btn>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="text" @click="refreshQrCode" :disabled="qrDialog.loading" size="small"
            prepend-icon="mdi-refresh">
            刷新二维码
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue';

const props = defineProps({
  api: {
    type: [Object, Function],
    required: true
  },
  initialConfig: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(['save', 'close', 'switch']);

// 定义插件ID常量，修复pluginId未定义错误
const PLUGIN_ID = "P115StrmHelper";

// 状态变量
const loading = ref(true);
const saveLoading = ref(false);
const syncLoading = ref(false);
const shareSyncLoading = ref(false);
const activeTab = ref('tab-transfer');
const mediaservers = ref([]);
const isCookieVisible = ref(false);
const config = reactive({
  language: "zh_CN",
  enabled: false,
  notify: false,
  strm_url_format: 'pickcode',
  link_redirect_mode: 'cookie',
  cookies: '',
  password: '',
  moviepilot_address: '',
  user_rmt_mediaext: 'mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v',
  user_download_mediaext: 'srt,ssa,ass',
  transfer_monitor_enabled: false,
  transfer_monitor_scrape_metadata_enabled: false,
  transfer_monitor_scrape_metadata_exclude_paths: '',
  transfer_monitor_paths: '',
  transfer_mp_mediaserver_paths: '',
  transfer_monitor_media_server_refresh_enabled: false,
  transfer_monitor_mediaservers: [],
  timing_full_sync_strm: false,
  full_sync_overwrite_mode: "never",
  full_sync_remove_unless_strm: false,
  full_sync_auto_download_mediainfo_enabled: false,
  full_sync_strm_log: true,
  full_sync_batch_num: 5000,
  full_sync_process_num: 128,
  cron_full_sync_strm: '0 */7 * * *',
  full_sync_strm_paths: '',
  full_sync_iter_function: 'iter_files_with_path_skim',
  increment_sync_strm_enabled: false,
  increment_sync_auto_download_mediainfo_enabled: false,
  increment_sync_cron: "0 * * * *",
  increment_sync_strm_paths: '',
  increment_sync_mp_mediaserver_paths: '',
  increment_sync_scrape_metadata_enabled: false,
  increment_sync_scrape_metadata_exclude_paths: '',
  increment_sync_media_server_refresh_enabled: false,
  increment_sync_mediaservers: [],
  monitor_life_enabled: false,
  monitor_life_auto_download_mediainfo_enabled: false,
  monitor_life_paths: '',
  monitor_life_mp_mediaserver_paths: '',
  monitor_life_media_server_refresh_enabled: false,
  monitor_life_mediaservers: [],
  monitor_life_event_modes: [],
  monitor_life_scrape_metadata_enabled: false,
  monitor_life_scrape_metadata_exclude_paths: '',
  share_strm_auto_download_mediainfo_enabled: false,
  user_share_code: '',
  user_receive_code: '',
  user_share_link: '',
  user_share_pan_path: '/',
  user_share_local_path: '',
  clear_recyclebin_enabled: false,
  clear_receive_path_enabled: false,
  cron_clear: '0 */7 * * *',
  pan_transfer_enabled: false,
  pan_transfer_paths: '',
  directory_upload_enabled: false,
  directory_upload_mode: 'compatibility',
  directory_upload_uploadext: 'mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v',
  directory_upload_copyext: 'srt,ssa,ass',
  directory_upload_path: [],
  cloudsaver_url: '',
  cloudsaver_username: '',
  cloudsaver_password: '',
  nullbr_app_id: '',
  nullbr_api_key: '',
  same_playback: false
});

// 消息提示
const message = reactive({
  text: '',
  type: 'info'
});

// 路径管理
const transferPaths = ref([{ local: '', remote: '' }]);
const transferMpPaths = ref([{ local: '', remote: '' }]);
const fullSyncPaths = ref([{ local: '', remote: '' }]);
const incrementSyncPaths = ref([{ local: '', remote: '' }]);
const incrementSyncMPPaths = ref([{ local: '', remote: '' }]);
const monitorLifePaths = ref([{ local: '', remote: '' }]);
const monitorLifeMpPaths = ref([{ local: '', remote: '' }]);
const panTransferPaths = ref([{ path: '' }]);
const transferExcludePaths = ref([{ path: '' }]);
const incrementSyncExcludePaths = ref([{ local: '', remote: '' }]);
const monitorLifeExcludePaths = ref([{ path: '' }]);
const directoryUploadPaths = ref([{ src: '', dest_remote: '', dest_local: '', delete: false }]);
const fullSyncConfirmDialog = ref(false);

// 目录选择器对话框
const dirDialog = reactive({
  show: false,
  isLocal: true,
  loading: false,
  error: null,
  currentPath: '/',
  items: [],
  selectedPath: '',
  callback: null,
  type: '',
  index: -1,
  fieldKey: null,
  targetConfigKeyForExclusion: null,
  originalPathTypeBackup: '',
  originalIndexBackup: -1
});

// 二维码登录对话框
const qrDialog = reactive({
  show: false,
  loading: false,
  error: null,
  qrcode: '',
  uid: '',
  time: "",
  sgin: "",
  tips: '请使用支付宝扫描二维码登录',
  status: '等待扫码',
  checkInterval: null,
  clientType: 'alipaymini'
});

// 二维码客户端类型选项
const clientTypes = [
  { label: "支付宝", value: "alipaymini" },
  { label: "微信", value: "wechatmini" },
  { label: "安卓", value: "115android" },
  { label: "iOS", value: "115ios" },
  { label: "网页", value: "web" },
  { label: "PAD", value: "115ipad" },
  { label: "TV", value: "tv" }
];

// 监视config中的路径配置，同步到可视化组件
watch(() => config.transfer_monitor_paths, (newVal) => {
  if (!newVal) {
    transferPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    transferPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (transferPaths.value.length === 0) {
      transferPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析transfer_monitor_paths出错:', e);
    transferPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.transfer_mp_mediaserver_paths, (newVal) => {
  if (!newVal) {
    transferMpPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    transferMpPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (transferMpPaths.value.length === 0) {
      transferMpPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析transfer_mp_mediaserver_paths出错:', e);
    transferMpPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.full_sync_strm_paths, (newVal) => {
  if (!newVal) {
    fullSyncPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    fullSyncPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (fullSyncPaths.value.length === 0) {
      fullSyncPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析full_sync_strm_paths出错:', e);
    fullSyncPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.increment_sync_strm_paths, (newVal) => {
  if (!newVal) {
    incrementSyncPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    incrementSyncPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (incrementSyncPaths.value.length === 0) {
      incrementSyncPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析increment_sync_strm_paths出错:', e);
    incrementSyncPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.increment_sync_mp_mediaserver_paths, (newVal) => {
  if (!newVal) {
    incrementSyncMPPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    incrementSyncMPPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (incrementSyncMPPaths.value.length === 0) {
      incrementSyncMPPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析increment_sync_mp_mediaserver_paths出错:', e);
    incrementSyncMPPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.monitor_life_paths, (newVal) => {
  if (!newVal) {
    monitorLifePaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    monitorLifePaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (monitorLifePaths.value.length === 0) {
      monitorLifePaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析monitor_life_paths出错:', e);
    monitorLifePaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.monitor_life_mp_mediaserver_paths, (newVal) => {
  if (!newVal) {
    monitorLifeMpPaths.value = [{ local: '', remote: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    monitorLifeMpPaths.value = paths.map(path => {
      const parts = path.split('#');
      return { local: parts[0] || '', remote: parts[1] || '' };
    });

    if (monitorLifeMpPaths.value.length === 0) {
      monitorLifeMpPaths.value = [{ local: '', remote: '' }];
    }
  } catch (e) {
    console.error('解析monitor_life_mp_mediaserver_paths出错:', e);
    monitorLifeMpPaths.value = [{ local: '', remote: '' }];
  }
}, { immediate: true });

watch(() => config.pan_transfer_paths, (newVal) => {
  if (!newVal) {
    panTransferPaths.value = [{ path: '' }];
    return;
  }

  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    panTransferPaths.value = paths.map(path => {
      return { path };
    });

    if (panTransferPaths.value.length === 0) {
      panTransferPaths.value = [{ path: '' }];
    }
  } catch (e) {
    console.error('解析pan_transfer_paths出错:', e);
    panTransferPaths.value = [{ path: '' }];
  }
}, { immediate: true });

// 新增：监视 exclude_paths 字符串与数组之间的同步
watch(() => config.transfer_monitor_scrape_metadata_exclude_paths, (newVal) => {
  if (typeof newVal !== 'string' || !newVal.trim()) {
    transferExcludePaths.value = [{ path: '' }];
    return;
  }
  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    transferExcludePaths.value = paths.map(p => ({ path: p }));
    if (transferExcludePaths.value.length === 0) {
      transferExcludePaths.value = [{ path: '' }];
    }
  } catch (e) {
    console.error('解析 transfer_monitor_scrape_metadata_exclude_paths 出错:', e);
    transferExcludePaths.value = [{ path: '' }];
  }
}, { immediate: true });

watch(transferExcludePaths, (newVal) => {
  if (!Array.isArray(newVal)) return;
  const pathsString = newVal
    .map(item => item.path?.trim())
    .filter(p => p)
    .join('\n');
  if (config.transfer_monitor_scrape_metadata_exclude_paths !== pathsString) {
    config.transfer_monitor_scrape_metadata_exclude_paths = pathsString;
  }
}, { deep: true });

watch(() => config.increment_sync_scrape_metadata_exclude_paths, (newVal) => {
  if (typeof newVal !== 'string' || !newVal.trim()) {
    incrementSyncExcludePaths.value = [{ path: '' }];
    return;
  }
  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    incrementSyncExcludePaths.value = paths.map(p => ({ path: p }));
    if (incrementSyncExcludePaths.value.length === 0) {
      incrementSyncExcludePaths.value = [{ path: '' }];
    }
  } catch (e) {
    console.error('解析 increment_sync_scrape_metadata_exclude_paths 出错:', e);
    incrementSyncExcludePaths.value = [{ path: '' }];
  }
}, { immediate: true });

watch(incrementSyncExcludePaths, (newVal) => {
  if (!Array.isArray(newVal)) return;
  const pathsString = newVal
    .map(item => item.path?.trim())
    .filter(p => p)
    .join('\n');
  if (config.increment_sync_scrape_metadata_exclude_paths !== pathsString) {
    config.increment_sync_scrape_metadata_exclude_paths = pathsString;
  }
}, { deep: true });

watch(() => config.monitor_life_scrape_metadata_exclude_paths, (newVal) => {
  if (typeof newVal !== 'string' || !newVal.trim()) {
    monitorLifeExcludePaths.value = [{ path: '' }];
    return;
  }
  try {
    const paths = newVal.split('\n').filter(line => line.trim());
    monitorLifeExcludePaths.value = paths.map(p => ({ path: p }));
    if (monitorLifeExcludePaths.value.length === 0) {
      monitorLifeExcludePaths.value = [{ path: '' }];
    }
  } catch (e) {
    console.error('解析 monitor_life_scrape_metadata_exclude_paths 出错:', e);
    monitorLifeExcludePaths.value = [{ path: '' }];
  }
}, { immediate: true });

watch(monitorLifeExcludePaths, (newVal) => {
  if (!Array.isArray(newVal)) return;
  const pathsString = newVal
    .map(item => item.path?.trim())
    .filter(p => p)
    .join('\n');
  if (config.monitor_life_scrape_metadata_exclude_paths !== pathsString) {
    config.monitor_life_scrape_metadata_exclude_paths = pathsString;
  }
}, { deep: true });

// 从路径对象列表生成配置字符串
const generatePathsConfig = (paths, key) => {
  const configText = paths.map(p => {
    if (key === 'panTransfer') {
      return p.path?.trim();
    } else {
      return `${p.local?.trim()}#${p.remote?.trim()}`;
    }
  }).filter(p => {
    if (key === 'panTransfer') {
      return p && p !== '';
    } else {
      return p !== '#' && p !== '';
    }
  }).join('\n');

  return configText;
};

// 加载配置
const loadConfig = async () => {
  try {
    loading.value = true;
    const data = await props.api.get(`plugin/${PLUGIN_ID}/get_config`);
    if (data) {
      // 更新配置
      Object.assign(config, data);

      // 初始化 directoryUploadPaths
      directoryUploadPaths.value = (Array.isArray(config.directory_upload_path) && config.directory_upload_path.length > 0)
        ? JSON.parse(JSON.stringify(config.directory_upload_path))
        : [{ src: '', dest_remote: '', dest_local: '', delete: false }];

      // 保存媒体服务器列表
      if (data.mediaservers) {
        mediaservers.value = data.mediaservers;
      }

      const p115LocalPaths = new Set();
      if (config.transfer_monitor_paths) {
        config.transfer_monitor_paths.split('\n')
          .map(p => p.split('#')[0]?.trim()).filter(p => p).forEach(p => p115LocalPaths.add(p));
      }
      if (config.full_sync_strm_paths) {
        config.full_sync_strm_paths.split('\n')
          .map(p => p.split('#')[0]?.trim()).filter(p => p).forEach(p => p115LocalPaths.add(p));
      }
      if (config.monitor_life_paths) {
        config.monitor_life_paths.split('\n')
          .map(p => p.split('#')[0]?.trim()).filter(p => p).forEach(p => p115LocalPaths.add(p));
      }

    }
  } catch (err) {
    console.error('加载配置失败:', err);
    message.text = `加载配置失败: ${err.message || '未知错误'}`;
    message.type = 'error';
  } finally {
    loading.value = false;
  }
};

// 保存配置
const saveConfig = async () => {
  saveLoading.value = true;
  message.text = '';
  message.type = 'info';

  try {
    // 1. 更新配置对象中的路径字符串 (这部分逻辑保持不变)
    config.transfer_monitor_paths = generatePathsConfig(transferPaths.value, 'transfer');
    config.transfer_mp_mediaserver_paths = generatePathsConfig(transferMpPaths.value, 'mp');
    config.full_sync_strm_paths = generatePathsConfig(fullSyncPaths.value, 'fullSync');
    config.increment_sync_strm_paths = generatePathsConfig(incrementSyncPaths.value, 'incrementSync');
    config.increment_sync_mp_mediaserver_paths = generatePathsConfig(incrementSyncMPPaths.value, 'increment-mp');
    config.monitor_life_paths = generatePathsConfig(monitorLifePaths.value, 'monitorLife');
    config.monitor_life_mp_mediaserver_paths = generatePathsConfig(monitorLifeMpPaths.value, 'monitorLifeMp');
    config.pan_transfer_paths = generatePathsConfig(panTransferPaths.value, 'panTransfer');
    config.directory_upload_path = directoryUploadPaths.value.filter(p => p.src?.trim() || p.dest_remote?.trim() || p.dest_local?.trim());

    // 2. 【重要】通过 emit 事件将配置数据发送给 MoviePilot 框架
    //    使用 JSON.parse(JSON.stringify(...)) 确保传递的是纯对象
    emit('save', JSON.parse(JSON.stringify(config)));

    // 3. (可选) 显示本地的临时反馈信息
    message.text = '配置已发送保存请求，请稍候...';
    message.type = 'info';

    // 注意：不再需要检查后端API的响应，因为保存由框架处理
    // 注意：也不再需要返回 true/false，因为操作是异步触发的

  } catch (err) {
    // 这个 catch 块现在主要处理 emit 或 generatePathsConfig 可能出现的错误
    console.error('发送保存事件时出错:', err);
    message.text = `发送保存请求时出错: ${err.message || '未知错误'}`;
    message.type = 'error';
  } finally {
    saveLoading.value = false;
    // 延迟清除临时消息
    setTimeout(() => {
      // 只清除临时的 'info' 或 'error' 消息
      if (message.type === 'info' || message.type === 'error') {
        message.text = '';
      }
    }, 5000);
  }
};

const handleConfirmFullSync = async () => {
  fullSyncConfirmDialog.value = false; // 先关闭对话框
  await triggerFullSync(); // 然后执行原始的同步函数
};

// 触发全量同步
const triggerFullSync = async () => {
  syncLoading.value = true;
  message.text = '';

  try {
    // 检查插件是否已启用
    if (!config.enabled) {
      throw new Error('插件未启用，请先启用插件');
    }

    // 检查是否已配置Cookie
    if (!config.cookies || config.cookies.trim() === '') {
      throw new Error('请先设置115 Cookie');
    }

    // 同步路径设置到配置对象
    config.full_sync_strm_paths = generatePathsConfig(fullSyncPaths.value, 'fullSync');

    // 检查是否有有效路径配置
    if (!config.full_sync_strm_paths) {
      throw new Error('请先配置全量同步路径');
    }

    // 使用常量PLUGIN_ID

    // 调用API触发全量同步
    const result = await props.api.post(`plugin/${PLUGIN_ID}/full_sync`);

    if (result && result.code === 0) {
      message.text = result.msg || '全量同步任务已启动';
      message.type = 'success';
    } else {
      throw new Error(result?.msg || '启动全量同步失败');
    }
  } catch (err) {
    message.text = `启动全量同步失败: ${err.message || '未知错误'}`;
    message.type = 'error';
    console.error('启动全量同步失败:', err);
  } finally {
    syncLoading.value = false;
  }
};

// 触发分享同步
const triggerShareSync = async () => {
  shareSyncLoading.value = true;
  message.text = '';

  try {
    // 检查插件是否已启用
    if (!config.enabled) {
      throw new Error('插件未启用，请先启用插件');
    }

    // 检查是否已配置Cookie
    if (!config.cookies || config.cookies.trim() === '') {
      throw new Error('请先设置115 Cookie');
    }

    // 检查是否配置了分享目标路径
    if (!config.share_target_path || config.share_target_path.trim() === '') {
      throw new Error('请先配置分享目标路径');
    }

    // 检查是否配置了分享STRM路径
    if (!config.share_strm_path || config.share_strm_path.trim() === '') {
      throw new Error('请先配置分享STRM路径');
    }

    // 使用常量PLUGIN_ID

    // 调用API触发分享同步
    const result = await props.api.post(`plugin/${PLUGIN_ID}/share_sync`);

    if (result && result.code === 0) {
      message.text = result.msg || '分享同步任务已启动';
      message.type = 'success';
    } else {
      throw new Error(result?.msg || '启动分享同步失败');
    }
  } catch (err) {
    message.text = `启动分享同步失败: ${err.message || '未知错误'}`;
    message.type = 'error';
    console.error('启动分享同步失败:', err);
  } finally {
    shareSyncLoading.value = false;
  }
};

// 路径管理方法
const addPath = (type) => {
  switch (type) {
    case 'transfer':
      transferPaths.value.push({ local: '', remote: '' });
      break;
    case 'mp':
      transferMpPaths.value.push({ local: '', remote: '' });
      break;
    case 'fullSync':
      fullSyncPaths.value.push({ local: '', remote: '' });
      break;
    case 'incrementSync':
      incrementSyncPaths.value.push({ local: '', remote: '' });
      break;
    case 'increment-mp':
      incrementSyncMPPaths.value.push({ local: '', remote: '' });
      break;
    case 'monitorLife':
      monitorLifePaths.value.push({ local: '', remote: '' });
      break;
    case 'monitorLifeMp':
      monitorLifeMpPaths.value.push({ local: '', remote: '' });
      break;
    case 'directoryUpload':
      directoryUploadPaths.value.push({ src: '', dest_remote: '', dest_local: '', delete: false });
      break;
  }
};

const removePath = (index, type) => {
  switch (type) {
    case 'transfer':
      transferPaths.value.splice(index, 1);
      if (transferPaths.value.length === 0) {
        transferPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'mp':
      transferMpPaths.value.splice(index, 1);
      if (transferMpPaths.value.length === 0) {
        transferMpPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'fullSync':
      fullSyncPaths.value.splice(index, 1);
      if (fullSyncPaths.value.length === 0) {
        fullSyncPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'incrementSync':
      incrementSyncPaths.value.splice(index, 1);
      if (incrementSyncPaths.value.length === 0) {
        incrementSyncPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'increment-mp':
      incrementSyncMPPaths.value.splice(index, 1);
      if (incrementSyncMPPaths.value.length === 0) {
        incrementSyncMPPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'monitorLife':
      monitorLifePaths.value.splice(index, 1);
      if (monitorLifePaths.value.length === 0) {
        monitorLifePaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'monitorLifeMp':
      monitorLifeMpPaths.value.splice(index, 1);
      if (monitorLifeMpPaths.value.length === 0) {
        monitorLifeMpPaths.value = [{ local: '', remote: '' }];
      }
      break;
    case 'directoryUpload':
      directoryUploadPaths.value.splice(index, 1);
      if (directoryUploadPaths.value.length === 0) {
        directoryUploadPaths.value = [{ src: '', dest_remote: '', dest_local: '', delete: false }];
      }
      break;
  }
};

const addPanTransferPath = () => {
  panTransferPaths.value.push({ path: '' });
};

const removePanTransferPath = (index) => {
  panTransferPaths.value.splice(index, 1);
  if (panTransferPaths.value.length === 0) {
    panTransferPaths.value = [{ path: '' }];
  }
};

// 目录选择器方法
const openDirSelector = (index, locationType, pathType, fieldKey = null) => {
  dirDialog.show = true;
  dirDialog.isLocal = locationType === 'local';
  dirDialog.loading = false;
  dirDialog.error = null;
  dirDialog.items = [];
  dirDialog.index = index;
  dirDialog.type = pathType;
  dirDialog.fieldKey = fieldKey;
  dirDialog.targetConfigKeyForExclusion = null;
  dirDialog.originalPathTypeBackup = '';
  dirDialog.originalIndexBackup = -1;

  // 设置初始路径
  if (dirDialog.isLocal) {
    dirDialog.currentPath = '/';
  } else {
    dirDialog.currentPath = '/';
  }

  // 加载目录内容
  loadDirContent();
};

const loadDirContent = async () => {
  dirDialog.loading = true;
  dirDialog.error = null;
  dirDialog.items = [];

  try {
    // 本地目录浏览
    if (dirDialog.isLocal) {
      try {
        // 使用MoviePilot的文件管理API
        const response = await props.api.post('storage/list', {
          path: dirDialog.currentPath || '/',
          type: 'share', // 使用默认的share类型
          flag: 'ROOT'
        });

        if (response && Array.isArray(response)) {
          dirDialog.items = response
            .filter(item => item.type === 'dir') // 只保留目录
            .map(item => ({
              name: item.name,
              path: item.path,
              is_dir: true
            }))
            .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
        } else {
          throw new Error('浏览目录失败：无效响应');
        }
      } catch (error) {
        console.error('浏览本地目录失败:', error);
        dirDialog.error = `浏览本地目录失败: ${error.message || '未知错误'}`;
        dirDialog.items = [];
      }
    }
    // 115网盘目录浏览
    else {
      // 使用常量PLUGIN_ID

      // 检查cookie是否已设置
      if (!config.cookies || config.cookies.trim() === '') {
        throw new Error('请先设置115 Cookie才能浏览网盘目录');
      }

      // 调用API获取目录内容
      const result = await props.api.get(`plugin/${PLUGIN_ID}/browse_dir?path=${encodeURIComponent(dirDialog.currentPath)}&is_local=${dirDialog.isLocal}`);

      if (result && result.code === 0 && result.items) {
        dirDialog.items = result.items
          .filter(item => item.is_dir) // 只保留目录
          .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
        dirDialog.currentPath = result.path || dirDialog.currentPath;
      } else {
        throw new Error(result?.msg || '获取网盘目录内容失败');
      }
    }
  } catch (error) {
    console.error('加载目录内容失败:', error);
    dirDialog.error = error.message || '获取目录内容失败';

    // 如果是Cookie错误，清空目录列表
    if (error.message.includes('Cookie') || error.message.includes('cookie')) {
      dirDialog.items = [];
    }
  } finally {
    dirDialog.loading = false;
  }
};

const selectDir = (item) => {
  if (!item || !item.is_dir) return;

  if (item.path) {
    dirDialog.currentPath = item.path;
    loadDirContent();
  }
};

const navigateToParentDir = () => {
  const path = dirDialog.currentPath;

  // If it's a remote path (115 Pan), use simple, explicit POSIX path logic.
  // This prevents any Windows-style path contamination.
  if (!dirDialog.isLocal) {
    if (path === '/') return; // Already at root

    // Normalize and remove any trailing slash (unless it's the root)
    let current = path.replace(/\\/g, '/');
    if (current.length > 1 && current.endsWith('/')) {
      current = current.slice(0, -1);
    }

    const parent = current.substring(0, current.lastIndexOf('/'));

    // If the parent is empty, it means we were in a top-level directory (e.g., '/movies'), so the parent is the root.
    dirDialog.currentPath = parent === '' ? '/' : parent;

    loadDirContent();
    return; // IMPORTANT: Stop execution to not use the local path logic below.
  }

  if (path === '/' || path === 'C:\\' || path === 'C:/') return;

  // 统一使用正斜杠处理路径
  const normalizedPath = path.replace(/\\/g, '/');
  const parts = normalizedPath.split('/').filter(Boolean);

  if (parts.length === 0) {
    dirDialog.currentPath = '/';
  } else if (parts.length === 1 && normalizedPath.includes(':')) {
    // Windows驱动器根目录
    dirDialog.currentPath = parts[0] + ':/';
  } else {
    // 移除最后一个部分
    parts.pop();
    dirDialog.currentPath = parts.length === 0 ? '/' :
      (normalizedPath.startsWith('/') ? '/' : '') +
      parts.join('/') + '/';
  }

  loadDirContent();
};

const confirmDirSelection = () => {
  if (!dirDialog.currentPath) return;

  let processedPath = dirDialog.currentPath;
  // 移除末尾的斜杠，除非路径是 "/" 或者类似 "C:/" 的驱动器根目录
  if (processedPath !== '/' &&
    !(/^[a-zA-Z]:[\\\/]$/.test(processedPath)) &&
    (processedPath.endsWith('/') || processedPath.endsWith('\\\\'))) {
    processedPath = processedPath.slice(0, -1);
  }

  // Handle exclusion path selection by adding to the respective array
  if (dirDialog.type === 'excludePath' && dirDialog.targetConfigKeyForExclusion) {
    const targetKey = dirDialog.targetConfigKeyForExclusion;
    let targetArrayRef;

    if (targetKey === 'transfer_monitor_scrape_metadata_exclude_paths') {
      targetArrayRef = transferExcludePaths;
    } else if (targetKey === 'monitor_life_scrape_metadata_exclude_paths') {
      targetArrayRef = monitorLifeExcludePaths;
    } else if (targetKey === 'increment_sync_scrape_metadata_exclude_paths') {
      targetArrayRef = incrementSyncExcludePaths;
    }

    if (targetArrayRef) {
      // If the array contains only one empty path, replace it. Otherwise, add a new path.
      if (targetArrayRef.value.length === 1 && !targetArrayRef.value[0].path) {
        targetArrayRef.value[0] = { path: processedPath };
      } else {
        // Prevent adding duplicate paths
        if (!targetArrayRef.value.some(item => item.path === processedPath)) {
          targetArrayRef.value.push({ path: processedPath });
        } else {
          message.text = '该排除路径已存在。';
          message.type = 'warning';
          setTimeout(() => { message.text = ''; }, 3000);
        }
      }
    }

    // Restore original dialog type and index from backup, then clear them
    dirDialog.type = dirDialog.originalPathTypeBackup;
    dirDialog.index = dirDialog.originalIndexBackup;
    dirDialog.targetConfigKeyForExclusion = null;
    dirDialog.originalPathTypeBackup = '';
    dirDialog.originalIndexBackup = -1;
  }
  // Handle original path selection logic for path mappings
  else if (dirDialog.index >= 0 && dirDialog.type !== 'excludePath') {
    switch (dirDialog.type) {
      case 'transfer':
        if (dirDialog.isLocal) {
          transferPaths.value[dirDialog.index].local = processedPath;
        } else {
          transferPaths.value[dirDialog.index].remote = processedPath;
        }
        break;
      case 'fullSync':
        if (dirDialog.isLocal) {
          fullSyncPaths.value[dirDialog.index].local = processedPath;
        } else {
          fullSyncPaths.value[dirDialog.index].remote = processedPath;
        }
        break;
      case 'incrementSync':
        if (dirDialog.isLocal) {
          incrementSyncPaths.value[dirDialog.index].local = processedPath;
        } else {
          incrementSyncPaths.value[dirDialog.index].remote = processedPath;
        }
        break;
      case 'monitorLife':
        if (dirDialog.isLocal) {
          monitorLifePaths.value[dirDialog.index].local = processedPath;
        } else {
          monitorLifePaths.value[dirDialog.index].remote = processedPath;
        }
        break;
      case 'panTransfer':
        panTransferPaths.value[dirDialog.index].path = processedPath;
        break;
      case 'directoryUpload':
        if (dirDialog.fieldKey && directoryUploadPaths.value[dirDialog.index]) {
          directoryUploadPaths.value[dirDialog.index][dirDialog.fieldKey] = processedPath;
        }
        break;
    }
  } else if (dirDialog.type === 'sharePath') {
    // 这个分支主要用于 Page.vue 的分享路径，Config.vue 目前不直接使用此 type 进行赋值
    // 但保留逻辑以防未来扩展或共享组件
    if (dirDialog.isLocal) {
      config.user_share_local_path = processedPath;
    } else {
      config.user_share_pan_path = processedPath;
    }
  }

  // 关闭对话框
  closeDirDialog();
};

const closeDirDialog = () => {
  dirDialog.show = false;
  dirDialog.items = [];
  dirDialog.error = null;
};

// 新增：复制Cookie到剪贴板
const copyCookieToClipboard = async () => {
  if (!config.cookies) {
    message.text = 'Cookie为空，无法复制。';
    message.type = 'warning';
    return;
  }
  try {
    await navigator.clipboard.writeText(config.cookies);
    message.text = 'Cookie已复制到剪贴板！';
    message.type = 'success';
  } catch (err) {
    console.error('复制Cookie失败:', err);
    message.text = '复制Cookie失败。请检查浏览器权限或确保通过HTTPS访问，或尝试手动复制。';
    message.type = 'error';
  }
  setTimeout(() => {
    if (message.type === 'success' || message.type === 'warning' || message.type === 'error') {
      message.text = '';
    }
  }, 3000);
};

// 二维码登录方法
const openQrCodeDialog = () => {
  qrDialog.show = true;
  qrDialog.loading = false;
  qrDialog.error = null;
  qrDialog.qrcode = '';
  qrDialog.uid = '';
  qrDialog.time = '';
  qrDialog.sign = '';

  // 确保默认的 clientType 仍然是 clientTypes 中的一个有效值
  if (!clientTypes.some(ct => ct.value === qrDialog.clientType)) {
    qrDialog.clientType = 'alipaymini'; // 如果当前值无效，则重置为默认的支付宝
  }

  // 根据当前的 qrDialog.clientType 设置 tips
  const selectedClient = clientTypes.find(type => type.value === qrDialog.clientType);

  if (selectedClient) {
    qrDialog.tips = `请使用${selectedClient.label}扫描二维码登录`;
  } else {
    // 理应不会到这里，因为上面已经做了校验和重置
    qrDialog.clientType = 'alipaymini';
    qrDialog.tips = '请使用支付宝扫描二维码登录';
  }

  qrDialog.status = '等待扫码';
  getQrCode();
};

const getQrCode = async () => {
  qrDialog.loading = true;
  qrDialog.error = null;
  qrDialog.qrcode = '';
  qrDialog.uid = '';
  qrDialog.time = '';
  qrDialog.sign = '';

  // 在发送请求前打印实际使用的 clientType
  console.warn(`【115STRM助手 DEBUG】准备获取二维码，前端选择的 clientType: ${qrDialog.clientType}`);

  try {
    // 使用常量PLUGIN_ID
    const response = await props.api.get(`plugin/${PLUGIN_ID}/get_qrcode?client_type=${qrDialog.clientType}`);

    if (response && response.code === 0) {
      qrDialog.uid = response.uid;
      qrDialog.time = response.time;
      qrDialog.sign = response.sign;
      qrDialog.qrcode = response.qrcode;
      qrDialog.tips = response.tips || '请扫描二维码登录';
      qrDialog.status = '等待扫码';

      // 确保使用响应中的客户端类型，以防服务器调整
      if (response.client_type) {
        // console.warn(`【115STRM助手 DEBUG】后端返回 client_type: ${response.client_type}, 更新前端`);
        qrDialog.clientType = response.client_type;
      }

      startQrCodeCheckInterval();
    } else {
      qrDialog.error = response?.error || '获取二维码失败';
      // 增加日志，查看具体错误信息
      console.error("【115STRM助手 DEBUG】获取二维码API调用失败或返回错误码: ", response);
    }
  } catch (err) {
    qrDialog.error = `获取二维码出错: ${err.message || '未知错误'}`;
    console.error('【115STRM助手 DEBUG】获取二维码 JS 捕获异常:', err);
  } finally {
    qrDialog.loading = false;
  }
};

// 检查二维码状态
const checkQrCodeStatus = async () => {
  if (!qrDialog.uid || !qrDialog.show) return;
  if (!qrDialog.time || !qrDialog.show) return;
  if (!qrDialog.sign || !qrDialog.show) return;

  try {
    // 使用常量PLUGIN_ID
    const response = await props.api.get(`plugin/${PLUGIN_ID}/check_qrcode?uid=${qrDialog.uid}&time=${qrDialog.time}&sign=${qrDialog.sign}&client_type=${qrDialog.clientType}`);

    if (response && response.code === 0) {
      // 更新状态文本
      if (response.status === 'waiting') {
        qrDialog.status = '等待扫码';
      } else if (response.status === 'scanned') {
        qrDialog.status = '已扫码，请在设备上确认';
      } else if (response.status === 'success') {

        // 如果成功获取了cookie
        if (response.cookie) {
          // 停止轮询
          clearQrCodeCheckInterval();

          qrDialog.status = '登录成功！';

          // 更新配置中的 Cookie (前端显示会立即更新)
          config.cookies = response.cookie;

          // 【重要】不再自动触发保存事件 (emit)

          // 显示成功消息，提示用户需要手动保存
          message.text = '登录成功！Cookie已获取，请点击下方"保存配置"按钮保存。';
          message.type = 'success';

          // 延迟关闭 *仅* QR 对话框
          setTimeout(() => {
            qrDialog.show = false;
          }, 3000); // 3秒延迟，让用户看到消息

          // 移除之前的 emit 调用和相关处理

        } else {
          // status 为 success 但没有 cookie
          qrDialog.status = '登录似乎成功，但未获取到Cookie';
          message.text = '登录成功但未获取到Cookie信息，请重试或检查账号。';
          message.type = 'warning';
          // 停止轮询
          clearQrCodeCheckInterval();
        }
      }
    } else if (response && response.code === -1) {
      // 二维码出错或过期 (仅在非成功获取Cookie的情况下处理)
      if (qrDialog.status !== '登录成功，正在处理...') { // 避免覆盖成功后的状态
        clearQrCodeCheckInterval();
        qrDialog.error = response.error || '二维码已失效，请刷新';
        qrDialog.status = '二维码已失效';
      }
    }
  } catch (err) {
    // 仅在非成功获取Cookie的情况下处理网络等错误
    if (qrDialog.status !== '登录成功，正在处理...') {
      console.error('检查二维码状态JS捕获异常:', err);
      // 可以在这里添加一些错误提示，但要避免频繁报错干扰用户
      // qrDialog.error = `检查状态出错: ${err.message}`;
    }
  }
};

// 开始二维码状态检查定时器
const startQrCodeCheckInterval = () => {
  // 先清除可能存在的定时器
  clearQrCodeCheckInterval();

  // 设置新的定时器，每3秒检查一次
  qrDialog.checkIntervalId = setInterval(checkQrCodeStatus, 3000);
};

const clearQrCodeCheckInterval = () => {
  if (qrDialog.checkIntervalId) {
    clearInterval(qrDialog.checkIntervalId);
    qrDialog.checkIntervalId = null;
  }
};

const refreshQrCode = () => {
  // 清除之前的状态和定时器
  clearQrCodeCheckInterval();
  qrDialog.error = null;

  // 根据当前选择的客户端类型调整提示
  switch (qrDialog.clientType) {
    case 'alipaymini':
      qrDialog.tips = '请使用支付宝扫描二维码登录';
      break;
    case 'wechatmini':
      qrDialog.tips = '请使用微信扫描二维码登录';
      break;
    case '115android':
      qrDialog.tips = '请使用115安卓客户端扫描登录';
      break;
    case '115ios':
      qrDialog.tips = '请使用115 iOS客户端扫描登录';
      break;
    case 'web':
      qrDialog.tips = '请使用115网页版扫码登录';
      break;
    default:
      // 如果匹配不到，尝试从 clientTypes 数组中查找 label
      const matchedType = clientTypes.find(type => type.value === qrDialog.clientType);
      if (matchedType) {
        qrDialog.tips = `请使用${matchedType.label}扫描二维码登录`;
      } else {
        qrDialog.tips = '请扫描二维码登录'; // 最终回退
      }
  }

  // 重新获取二维码
  getQrCode();
};

const closeQrDialog = () => {
  clearQrCodeCheckInterval();
  qrDialog.show = false;
};

// 组件生命周期
onMounted(() => {
  loadConfig();
});

// 组件销毁时清理资源
const beforeUnmount = () => {
  clearQrCodeCheckInterval();
};

// 监听 qrDialog.clientType 的变化来调用 refreshQrCode
watch(() => qrDialog.clientType, (newVal, oldVal) => {
  // 仅当值实际改变且对话框可见时才刷新
  if (newVal !== oldVal && qrDialog.show) {
    console.log(`【115STRM助手 DEBUG】qrDialog.clientType 从 ${oldVal} 变为 ${newVal}，准备刷新二维码`);
    refreshQrCode();
  }
});

// 新增：设置MoviePilot地址为当前源
const setMoviePilotAddressToCurrentOrigin = () => {
  if (window && window.location && window.location.origin) {
    config.moviepilot_address = window.location.origin;
    message.text = 'MoviePilot地址已设置为当前站点地址！';
    message.type = 'success';
  } else {
    message.text = '无法获取当前站点地址。';
    message.type = 'error';
  }
  setTimeout(() => {
    if (message.type === 'success' || message.type === 'error') {
      message.text = '';
    }
  }, 3000);
};

// 新增：打开排除目录选择器的方法 (专用于本地目录选择)
const openExcludeDirSelector = (configKeyToUpdate) => {
  dirDialog.show = true;
  dirDialog.isLocal = true; // Always local for exclusion paths
  dirDialog.loading = false;
  dirDialog.error = null;
  dirDialog.items = [];
  dirDialog.currentPath = '/'; // 默认起始路径

  // Backup original type and index before overriding for exclusion path selection
  dirDialog.originalPathTypeBackup = dirDialog.type;
  dirDialog.originalIndexBackup = dirDialog.index;

  dirDialog.targetConfigKeyForExclusion = configKeyToUpdate;
  dirDialog.type = 'excludePath'; // Special type for this operation
  dirDialog.index = -1;           // Index is not relevant for appending to a textarea

  loadDirContent();
};

// 新增：移除排除目录条目
const removeExcludePathEntry = (index, type) => {
  let targetArrayRef;
  if (type === 'transfer_exclude') {
    targetArrayRef = transferExcludePaths;
  } else if (type === 'life_exclude') {
    targetArrayRef = monitorLifeExcludePaths;
  } else if (type === 'increment_exclude') {
    targetArrayRef = incrementSyncExcludePaths;
  }

  if (targetArrayRef && targetArrayRef.value && index < targetArrayRef.value.length) {
    targetArrayRef.value.splice(index, 1);
    if (targetArrayRef.value.length === 0) {
      // 保留一个空条目以触发 watcher 更新为空字符串，并为UI提供添加按钮的基础
      targetArrayRef.value = [{ path: '' }];
    }
  }
};
</script>

<style scoped>
/* 统一字体 - Inspired by Page.vue */
:deep(.v-card-title),
:deep(.v-card-text),
:deep(.v-list-item-title),
:deep(.v-list-item-subtitle),
:deep(.v-alert),
:deep(.v-btn),
:deep(.text-caption),
:deep(.text-subtitle-1),
:deep(.text-body-1),
:deep(.text-body-2) {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif !important;
}

/* 文字大小 - Unified with Page.vue */
:deep(.text-caption) {
  font-size: 0.8rem !important;
}

:deep(.text-body-2) {
  font-size: 0.85rem !important;
}

:deep(.text-subtitle-2) {
  /* Added for consistency with Page.vue inner card titles */
  font-size: 0.875rem !important;
  font-weight: 500 !important;
  line-height: 1.25rem !important;
}

:deep(.v-list-item-title) {
  font-size: 0.85rem !important;
  /* Unified with Page.vue's common list item title size */
}

:deep(.v-list-item-subtitle) {
  font-size: 0.8rem !important;
  /* Unified with Page.vue's common list item subtitle size */
}

/* 基本配置卡片样式 */
.config-card {
  border-radius: 8px !important;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)) !important;
  overflow: hidden;
  /* 确保内部元素不会超出圆角 */
}

.bg-primary-gradient {
  background: linear-gradient(to right, rgba(var(--v-theme-primary), 0.1), rgba(var(--v-theme-primary), 0.03)) !important;
  /* border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); */
}

.config-title {
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}

/* 路径输入框组 */
.path-group {
  padding: 8px;
  border: 1px solid rgba(var(--v-border-color), 0.3);
  border-radius: 6px;
}

.path-input-row {
  display: flex;
  align-items: center;
}

.path-input-field {
  flex-grow: 1;
}

.path-input-action {
  margin-left: 8px;
}

.v-list-item-title.text-danger {
  color: rgb(var(--v-theme-error)) !important;
  font-weight: bold;
}

/* Cookie 输入框样式 */
:deep(.v-textarea .v-field__input) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 0.8rem;
  line-height: 1.4;
}

/* Tab 样式调整 */
:deep(.v-tabs) {
  border-bottom: 2px solid rgba(var(--v-theme-primary), 0.5) !important;
}

:deep(.v-tab) {
  font-weight: 500;
  transition: all 0.3s ease;
}

:deep(.v-tab--selected) {
  background-color: rgba(var(--v-theme-primary), 0.1) !important;
  color: rgb(var(--v-theme-primary)) !important;
  border-radius: 6px 6px 0 0 !important;
  /* 左上和右上圆角 */
}

/* Switch 样式调整 */
:deep(.v-switch .v-selection-control__input > .v-icon) {
  color: rgba(var(--v-theme-medium-emphasis));
  /* 未激活时的滑块颜色 */
}

:deep(.v-switch .v-track) {
  background-color: rgba(var(--v-theme-medium-emphasis), 0.3) !important;
  /* 未激活时的轨道颜色 */
  opacity: 1 !important;
}

/* 调整字体大小 */
:deep(.v-card-text .v-label) {
  font-size: 0.9rem;
  /* 调整标签字体大小 */
}

:deep(.v-card-text .v-input__details) {
  font-size: 0.8rem !important;
  /* Ensure input hints also match .text-caption */
}

:deep(.v-text-field input),
:deep(.v-textarea textarea) {
  font-size: 0.875rem !important;
}

/* Reduce vertical padding for columns within rows */
:deep(.v-row > .v-col) {
  padding-top: 4px !important;
  padding-bottom: 4px !important;
}

/* 更鲜艳的 Tab 颜色 (示例) */
:deep(.v-tabs .v-tab--selected) {
  background-color: #1976D2 !important;
  /* Vuetify 主题蓝色 */
  color: white !important;
}

:deep(.v-tabs .v-tab) {
  color: #424242;
  /* 深灰色 */
}

:deep(.v-tabs) {
  border-bottom: 2px solid #1976D2 !important;
  /* Vuetify 主题蓝色 */
}

/* Colorful Switches */
:deep(.v-switch .v-selection-control--dirty .v-track) {
  opacity: 0.8 !important;
  /* Ensure high opacity for color visibility */
}

:deep(.v-switch .v-selection-control--dirty .v-selection-control__input > .v-icon) {
  color: white !important;
}

/* Primary Color Switch */
:deep(v-switch[color="primary"] .v-selection-control--dirty .v-track),
:deep(v-switch[color="primary"] .v-selection-control--dirty .v-switch__track) {
  /* track */
  background-color: rgb(var(--v-theme-primary)) !important;
  border-color: rgb(var(--v-theme-primary)) !important;
}

/* Success Color Switch */
:deep(v-switch[color="success"] .v-selection-control--dirty .v-track),
:deep(v-switch[color="success"] .v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-success)) !important;
  border-color: rgb(var(--v-theme-success)) !important;
}

/* Info Color Switch */
:deep(v-switch[color="info"] .v-selection-control--dirty .v-track),
:deep(v-switch[color="info"] .v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-info)) !important;
  border-color: rgb(var(--v-theme-info)) !important;
}

/* Warning Color Switch */
:deep(v-switch[color="warning"] .v-selection-control--dirty .v-track),
:deep(v-switch[color="warning"] .v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-warning)) !important;
  border-color: rgb(var(--v-theme-warning)) !important;
}

/* Error Color Switch */
:deep(v-switch[color="error"] .v-selection-control--dirty .v-track),
:deep(v-switch[color="error"] .v-selection-control--dirty .v-switch__track) {
  background-color: rgb(var(--v-theme-error)) !important;
  border-color: rgb(var(--v-theme-error)) !important;
}
</style>
