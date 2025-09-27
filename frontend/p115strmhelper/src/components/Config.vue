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
                <v-col cols="12" md="4">
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
                <!-- 阿里云盘 Token 配置 -->
                <v-col cols="12" md="4">
                  <v-text-field v-model="config.aliyundrive_token" label="阿里云盘 Token (可选)" hint="非必填。点击图标切换显隐、复制或扫码获取"
                    persistent-hint density="compact" variant="outlined" hide-details="auto"
                    :type="isAliTokenVisible ? 'text' : 'password'">
                    <template v-slot:append-inner>
                      <v-icon :icon="isAliTokenVisible ? 'mdi-eye-off' : 'mdi-eye'"
                        @click="isAliTokenVisible = !isAliTokenVisible"
                        :aria-label="isAliTokenVisible ? '隐藏Token' : '显示Token'"
                        :title="isAliTokenVisible ? '隐藏Token' : '显示Token'" class="mr-1" size="small"></v-icon>
                      <v-icon icon="mdi-content-copy" @click="copyAliTokenToClipboard"
                        :disabled="!config.aliyundrive_token" aria-label="复制Token" title="复制Token到剪贴板" size="small"
                        class="mr-1"></v-icon>
                    </template>
                    <template v-slot:append>
                      <v-icon icon="mdi-qrcode-scan" @click="openAliQrCodeDialog"
                        :color="config.aliyundrive_token ? 'success' : 'default'"
                        :aria-label="config.aliyundrive_token ? '更新/更换Token' : '扫码获取Token'"
                        :title="config.aliyundrive_token ? '更新/更换Token' : '扫码获取Token'"></v-icon>
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" md="4">
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
              <v-tab value="tab-cache-config" class="text-caption">
                <v-icon size="small" start>mdi-cached</v-icon>缓存配置
              </v-tab>
              <v-tab value="tab-data-enhancement" class="text-caption">
                <v-icon size="small" start>mdi-database-eye-outline</v-icon>数据增强
              </v-tab>
              <v-tab value="tab-advanced-configuration" class="text-caption">
                <v-icon size="small" start>mdi-tune</v-icon>高级配置
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
                      <v-col cols="12" md="3">
                        <v-select v-model="config.full_sync_overwrite_mode" label="覆盖模式" :items="[
                          { title: '总是', value: 'always' },
                          { title: '从不', value: 'never' }
                        ]" chips closable-chips></v-select>
                      </v-col>
                      <v-col cols="12" md="3">
                        <v-switch v-model="config.full_sync_remove_unless_strm" label="清理失效STRM文件"
                          color="warning"></v-switch>
                      </v-col>
                      <v-col cols="12" md="3">
                        <v-switch v-model="config.full_sync_remove_unless_dir" label="清理无效STRM目录"
                          color="warning" :disabled="!config.full_sync_remove_unless_strm"></v-switch>
                      </v-col>
                      <v-col cols="12" md="3">
                        <v-switch v-model="config.full_sync_remove_unless_file" label="清理无效STRM文件关联的媒体信息文件"
                          color="warning" :disabled="!config.full_sync_remove_unless_strm"></v-switch>
                      </v-col>
                    </v-row>

                    <v-row>
                      <v-col cols="12" md="3">
                        <v-switch v-model="config.timing_full_sync_strm" label="定期全量同步" color="info"></v-switch>
                      </v-col>
                      <v-col cols="12" md="3">
                        <VCronField v-model="config.cron_full_sync_strm" label="运行全量同步周期" hint="设置全量同步的执行周期"
                          persistent-hint density="compact"></VCronField>
                      </v-col>
                      <v-col cols="12" md="3">
                        <v-switch v-model="config.full_sync_auto_download_mediainfo_enabled" label="下载媒体数据文件"
                          color="warning"></v-switch>
                      </v-col>
                      <v-col cols="12" md="3">
                        <v-text-field v-model="fullSyncMinFileSizeFormatted" label="STRM最小文件大小"
                          hint="小于此值的文件将不生成STRM(单位K,M,G)" persistent-hint density="compact" placeholder="例如: 100M (可为空)"
                          clearable></v-text-field>
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
                    <v-col cols="12" md="6">
                      <VCronField v-model="config.increment_sync_cron" label="运行增量同步周期" hint="设置增量同步的执行周期"
                        persistent-hint density="compact"></VCronField>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-text-field v-model="incrementSyncMinFileSizeFormatted" label="STRM最小文件大小"
                        hint="小于此值的文件将不生成STRM(单位K,M,G)" persistent-hint density="compact" placeholder="例如: 100M (可为空)"
                        clearable></v-text-field>
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
                      <v-switch v-model="config.monitor_life_remove_mp_history" label="同步删除历史记录" color="warning"
                        :disabled="config.monitor_life_remove_mp_source"></v-switch>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-switch v-model="config.monitor_life_remove_mp_source" label="同步删除源文件" color="warning"
                        @change="value => { if (value) config.monitor_life_remove_mp_history = true }"></v-switch>
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

                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.monitor_life_auto_download_mediainfo_enabled" label="下载媒体数据文件"
                        color="warning"></v-switch>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.monitor_life_scrape_metadata_enabled" label="STRM自动刮削"
                        color="primary"></v-switch>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="monitorLifeMinFileSizeFormatted" label="STRM最小文件大小"
                        hint="小于此值的文件将不生成STRM(单位K,M,G)" persistent-hint density="compact" placeholder="例如: 100M (可为空)"
                        clearable></v-text-field>
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

                  <v-row class="mt-4">
                    <v-col cols="12">
                      <v-text-field v-model="config.pan_transfer_unrecognized_path" label="网盘整理未识别目录" density="compact"
                        append-icon="mdi-folder-network"
                        @click:append="openDirSelector('unrecognized', 'remote', 'panTransferUnrecognized')"></v-text-field>
                      <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                        提示：此目录用于存放整理过程中未能识别的媒体文件。
                      </v-alert>
                      <v-alert type="warning" variant="tonal" density="compact" class="mt-2">
                        注意：未识别目录不能设置在任何媒体库目录或待整理目录的内部。
                      </v-alert>
                    </v-col>
                  </v-row>

                  <v-divider class="my-3"></v-divider>

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
                    注意：<br>
                    1. 阿里云盘，115网盘分享链接秒传或转存都依赖于网盘整理<br>
                    2. TG/Slack资源搜索转存也依赖于网盘整理<br>
                    3. 当阿里云盘分享秒传未能识别分享媒体信息时，会自动将资源转存到网盘整理未识别目录，后续需要用户手动重命名整理
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

                  <!-- Nullbr 配置 -->
                  <v-card variant="outlined" class="mb-6">
                    <v-card-item>
                      <v-card-title class="d-flex align-center">
                        <v-icon start>mdi-cog-outline</v-icon>
                        <span class="text-h6">Nullbr 搜索配置</span>
                      </v-card-title>
                    </v-card-item>
                    <v-card-text>
                      <v-row>
                        <v-col cols="12" md="6">
                          <v-text-field v-model="config.nullbr_app_id" label="Nullbr APP ID" hint="从 Nullbr 官网申请"
                            persistent-hint density="compact" variant="outlined"></v-text-field>
                        </v-col>
                        <v-col cols="12" md="6">
                          <v-text-field v-model="config.nullbr_api_key" label="Nullbr API KEY" hint="从 Nullbr 官网申请"
                            persistent-hint density="compact" variant="outlined"></v-text-field>
                        </v-col>
                      </v-row>
                    </v-card-text>
                  </v-card>

                  <!-- 自定义频道搜索配置 -->
                  <v-card variant="outlined">
                    <v-card-item>
                      <v-card-title class="d-flex align-center">
                        <v-icon start>mdi-telegram</v-icon>
                        <span class="text-h6">自定义Telegram频道</span>
                      </v-card-title>
                    </v-card-item>
                    <v-card-text>
                      <div v-for="(channel, index) in tgChannels" :key="index" class="d-flex align-center mb-4">
                        <v-text-field v-model="channel.name" label="频道名称" placeholder="例如：爱影115资源分享频道" density="compact"
                          variant="outlined" hide-details class="mr-3"></v-text-field>
                        <v-text-field v-model="channel.id" label="频道ID" placeholder="例如：ayzgzf" density="compact"
                          variant="outlined" hide-details class="mr-3"></v-text-field>
                        <v-btn icon size="small" color="error" variant="tonal" @click="removeTgChannel(index)"
                          title="删除此频道">
                          <v-icon>mdi-delete-outline</v-icon>
                        </v-btn>
                      </div>

                      <!-- 操作按钮组 -->
                      <div class="d-flex ga-2">
                        <v-btn size="small" prepend-icon="mdi-plus-circle-outline" variant="tonal" color="primary"
                          @click="addTgChannel">
                          添加频道
                        </v-btn>
                        <v-btn size="small" prepend-icon="mdi-import" variant="tonal" @click="openImportDialog">
                          一键导入
                        </v-btn>
                      </div>
                    </v-card-text>
                  </v-card>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-6 text-caption">
                    <strong>Telegram频道搜索功能说明</strong><br>
                    - 您可以同时配置 Nullbr 和下方的自定义频道列表。<br>
                    - 系统会整合两者的搜索结果，为您提供更广泛的资源范围。
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

              <!-- 数据增强 -->
              <v-window-item value="tab-data-enhancement">
                <v-card-text>
                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.error_info_upload" label="错误信息上传" color="info"
                        density="compact"></v-switch>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.upload_module_enhancement" label="上传模块增强" color="info"
                        density="compact"></v-switch>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.transfer_module_enhancement" label="整理模块增强" color="info"
                        density="compact" :disabled="isTransferModuleEnhancementLocked" hint="此功能需要授权才能开启"
                        persistent-hint></v-switch>
                    </v-col>
                  </v-row>
                  <v-row>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.upload_share_info" label="上传分享链接" color="info"
                        density="compact"></v-switch>
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.upload_offline_info" label="上传离线下载链接" color="info"
                        density="compact"></v-switch>
                    </v-col>
                  </v-row>
                  <v-row>
                    <v-col cols="12" md="4" class="d-flex align-center">
                      <v-btn @click="getMachineId" size="small" prepend-icon="mdi-identifier">显示设备ID</v-btn>
                    </v-col>
                  </v-row>

                  <v-row v-if="machineId">
                    <v-col cols="12">
                      <v-text-field v-model="machineId" label="Machine ID" readonly density="compact" variant="outlined"
                        hide-details="auto"></v-text-field>
                    </v-col>
                  </v-row>

                  <!-- 上传模块增强配置 -->
                  <v-expansion-panels variant="tonal" class="mt-6">
                    <v-expansion-panel>
                      <v-expansion-panel-title>
                        <v-icon icon="mdi-tune-variant" class="mr-2"></v-icon>
                        上传模块增强配置
                      </v-expansion-panel-title>
                      <v-expansion-panel-text class="pa-4">
                        <v-row>
                          <v-col cols="12" md="4">
                            <v-switch v-model="config.upload_module_skip_slow_upload" label="秒传失败直接退出" color="info"
                              density="compact"></v-switch>
                          </v-col>
                          <v-col cols="12" md="4">
                            <v-switch v-model="config.upload_module_notify" label="秒传等待发送通知" color="info"
                              density="compact"></v-switch>
                          </v-col>
                        </v-row>
                        <v-row>
                          <v-col cols="12" md="6">
                            <v-text-field v-model.number="config.upload_module_wait_time" label="秒传休眠等待时间（单位秒）"
                              type="number" hint="秒传休眠等待时间（单位秒）" persistent-hint density="compact"></v-text-field>
                          </v-col>
                          <v-col cols="12" md="6">
                            <v-text-field v-model.number="config.upload_module_wait_timeout" label="秒传最长等待时间（单位秒）"
                              type="number" hint="秒传最长等待时间（单位秒）" persistent-hint density="compact"></v-text-field>
                          </v-col>
                        </v-row>
                        <v-row>
                          <v-col cols="12" md="6">
                            <v-text-field v-model="skipUploadWaitSizeFormatted" label="跳过等待秒传的文件大小阈值"
                              hint="文件小于此值将跳过等待秒传（单位支持K，M，G）" persistent-hint density="compact"
                              placeholder="例如: 5M, 1.5G (可为空)" clearable></v-text-field>
                          </v-col>
                          <v-col cols="12" md="6">
                            <v-text-field v-model="forceUploadWaitSizeFormatted" label="强制等待秒传的文件大小阈值"
                              hint="文件大于此值将强制等待秒传（单位支持K，M，G）" persistent-hint density="compact"
                              placeholder="例如: 5M, 1.5G (可为空)" clearable></v-text-field>
                          </v-col>
                        </v-row>
                        <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
                          <strong>秒传失败直接退出：</strong><br>
                          此功能开启后，对于无法秒传或者秒传等待超时的文件将直接跳过上传步骤，整理返回失败。
                        </v-alert>
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>

                  <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
                    <strong>115上传增强有效范围：</strong><br>
                    此功能开启后，将对整个MoviePilot系统内所有调用115网盘上传的功能生效。
                  </v-alert>

                  <v-alert type="warning" variant="tonal" density="compact" class="mt-3 text-caption">
                    <strong>风险与免责声明</strong><br>
                    - 插件程序内包含可选的Sentry分析组件，详见<a href="https://sentry.io/privacy/" target="_blank"
                      style="color: inherit; text-decoration: underline;">Sentry Privacy Policy</a>。<br>
                    - 插件程序将在必要时上传错误信息及运行环境信息。<br>
                    - 插件程序将记录程序运行重要节点并保存追踪数据至少72小时。
                  </v-alert>

                </v-card-text>
              </v-window-item>

              <v-window-item value="tab-advanced-configuration">
                <v-card-text>

                  <v-row>
                    <v-col cols="12">
                      <v-textarea v-model="config.strm_url_mode_custom" label="自定义STRM URL格式" variant="outlined"
                        rows="5" persistent-hint hint="为特定文件扩展名指定URL格式，优先级高于基础设置。格式：ext1,ext2 => format"
                        placeholder="例如：&#10;iso => pickname&#10;mp4,mkv => pickcode" clearable></v-textarea>
                    </v-col>
                  </v-row>
                  <v-alert type="info" variant="tonal" density="compact" class="mt-2 text-caption">
                    <strong>格式说明:</strong><br>
                    - 每行一条规则，格式为：`文件后缀 => URL格式`。<br>
                    - 左侧为文件扩展名(不含`.`)，多个后缀用英文逗号(`,`)分隔。<br>
                    - 右侧为URL格式，可选值为 `pickcode` 或 `pickname`。<br>
                    - 此处未指定的扩展名将使用 “基础设置” 中的 “STRM文件URL格式” 配置。<br>
                    - <strong>示例:</strong><br>
                    &nbsp;&nbsp;<code>iso => pickname</code> (iso文件使用 pickcode+name 格式)<br>
                    &nbsp;&nbsp;<code>mp4,mkv,ts => pickcode</code> (mp4, mkv, ts 文件使用 pickcode 格式)
                  </v-alert>

                  <v-row class="mt-4">
                    <v-col cols="12">
                      <v-combobox v-model="config.strm_generate_blacklist" label="STRM文件关键词过滤黑名单"
                        hint="输入关键词后按回车确认，可添加多个。包含这些词的视频文件将不会生成STRM文件。" persistent-hint multiple chips closable-chips
                        variant="outlined" density="compact"></v-combobox>
                    </v-col>
                  </v-row>

                  <v-row class="mt-4">
                    <v-col cols="12">
                      <v-combobox v-model="config.mediainfo_download_whitelist" label="媒体信息文件下载关键词过滤白名单"
                        hint="输入关键词后按回车确认，可添加多个。不包含这些词的媒体信息文件将不会下载。" persistent-hint multiple chips closable-chips
                        variant="outlined" density="compact"></v-combobox>
                    </v-col>
                  </v-row>

                  <v-row class="mt-4">
                    <v-col cols="12">
                      <v-combobox v-model="config.mediainfo_download_blacklist" label="媒体信息文件下载关键词过滤黑名单"
                        hint="输入关键词后按回车确认，可添加多个。包含这些词的媒体信息文件将不会下载。" persistent-hint multiple chips closable-chips
                        variant="outlined" density="compact"></v-combobox>
                    </v-col>
                  </v-row>

                  <v-row class="mt-4">
                    <v-col cols="12" md="4">
                      <v-switch v-model="config.strm_url_encode" label="STRM URL 文件名称编码" color="info" density="compact"
                        hint="启用后，STRM文件中的URL会对文件名进行编码处理"></v-switch>
                    </v-col>
                  </v-row>

                </v-card-text>
              </v-window-item>

              <!-- 缓存配置 -->
              <v-window-item value="tab-cache-config">
                <v-card-text>
                  <v-row>
                    <v-col cols="12">
                      <v-card variant="outlined" class="mb-4">
                        <v-card-item>
                          <v-card-title class="d-flex align-center">
                            <v-icon start>mdi-cached</v-icon>
                            <span class="text-h6">缓存管理</span>
                          </v-card-title>
                        </v-card-item>
                        <v-card-text>
                          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                            缓存清理功能可以帮助您清理插件运行过程中产生的缓存数据，解决部分因缓存导致的问题。
                          </v-alert>
                          
                          <v-row>
                            <v-col cols="12" md="6">
                              <v-card variant="outlined" class="pa-4 d-flex flex-column cache-card">
                                <div class="d-flex align-center mb-3">
                                  <v-icon color="primary" class="mr-2">mdi-folder-cog</v-icon>
                                  <span class="text-subtitle-1 font-weight-medium">清理文件路径ID缓存</span>
                                </div>
                                <p class="text-body-2 text-grey-darken-1 mb-3 flex-grow-1">
                                  清理文件路径ID缓存，包括目录ID到路径的映射缓存。
                                </p>
                                <v-btn 
                                  color="primary" 
                                  variant="outlined" 
                                  :loading="clearIdPathCacheLoading"
                                  @click="clearIdPathCache"
                                  prepend-icon="mdi-folder-cog"
                                  block
                                >
                                  清理文件路径ID缓存
                                </v-btn>
                              </v-card>
                            </v-col>
                            
                            <v-col cols="12" md="6">
                              <v-card variant="outlined" class="pa-4 d-flex flex-column cache-card">
                                <div class="d-flex align-center mb-3">
                                  <v-icon color="warning" class="mr-2">mdi-skip-next</v-icon>
                                  <span class="text-subtitle-1 font-weight-medium">清理增量同步跳过路径缓存</span>
                                </div>
                                <p class="text-body-2 text-grey-darken-1 mb-3 flex-grow-1">
                                  清理增量同步跳过路径缓存，重置增量同步的跳过路径记录，用于重新处理之前跳过的文件。
                                </p>
                                <v-btn 
                                  color="warning" 
                                  variant="outlined" 
                                  :loading="clearIncrementSkipCacheLoading"
                                  @click="clearIncrementSkipCache"
                                  prepend-icon="mdi-skip-next"
                                  block
                                >
                                  清理增量同步跳过路径缓存
                                </v-btn>
                              </v-card>
                            </v-col>
                          </v-row>
                        </v-card-text>
                      </v-card>
                    </v-col>
                  </v-row>
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

    <!-- 阿里云盘二维码登录对话框 -->
    <v-dialog v-model="aliQrDialog.show" max-width="450">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
          <v-icon icon="mdi-qrcode" class="mr-2" color="primary" size="small" />
          <span>阿里云盘扫码登录</span>
        </v-card-title>
        <v-card-text class="text-center py-4">
          <v-alert v-if="aliQrDialog.error" type="error" density="compact" class="mb-3 mx-3" variant="tonal" closable>
            {{ aliQrDialog.error }}
          </v-alert>
          <div v-if="aliQrDialog.loading" class="d-flex flex-column align-center py-3">
            <v-progress-circular indeterminate color="primary" class="mb-3"></v-progress-circular>
            <div>正在获取二维码...</div>
          </div>
          <div v-else-if="aliQrDialog.qrcode" class="d-flex flex-column align-center">
            <v-card flat class="border pa-2 mb-2">
              <img :src="aliQrDialog.qrcode" width="220" height="220" />
            </v-card>
            <div class="text-body-2 text-grey mb-1">请使用阿里云盘App扫描二维码</div>
            <div class="text-subtitle-2 font-weight-medium text-primary">{{ aliQrDialog.status }}</div>
          </div>
          <div v-else class="d-flex flex-column align-center py-3">
            <v-icon icon="mdi-qrcode-off" size="64" color="grey" class="mb-3"></v-icon>
            <div class="text-subtitle-1">二维码获取失败</div>
            <div class="text-body-2 text-grey">请点击刷新按钮重试</div>
          </div>
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="px-3 py-2">
          <v-btn color="grey" variant="text" @click="closeAliQrCodeDialog" size="small"
            prepend-icon="mdi-close">关闭</v-btn>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="text" @click="refreshAliQrCode" :disabled="aliQrDialog.loading" size="small"
            prepend-icon="mdi-refresh">
            刷新
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 一键导入频道配置对话框 -->
    <v-dialog v-model="importDialog.show" max-width="600" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
          <v-icon icon="mdi-import" class="mr-2" color="primary" size="small" />
          <span>一键导入频道配置</span>
        </v-card-title>
        <v-card-text class="py-4">
          <v-alert v-if="importDialog.error" type="error" density="compact" class="mb-3" variant="tonal" closable>
            {{ importDialog.error }}
          </v-alert>
          <p class="text-caption mb-2 text-grey-darken-1">
            请在此处粘贴JSON格式的频道列表。格式应为：<br>
            <code>[{"name":"名称1", "id":"id1"}, {"name":"名称2", "id":"id2"}]</code>
          </p>
          <v-textarea v-model="importDialog.jsonText" label="频道配置JSON" variant="outlined" rows="8" auto-grow
            hide-details="auto" placeholder='[{"name":"Lsp115","id":"Lsp115"}]'></v-textarea>
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="px-3 py-2">
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="closeImportDialog" size="small">
            取消
          </v-btn>
          <v-btn color="primary" variant="text" @click="handleConfirmImport" size="small">
            确认导入
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue';

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
const clearIdPathCacheLoading = ref(false);
const clearIncrementSkipCacheLoading = ref(false);
const activeTab = ref('tab-transfer');
const mediaservers = ref([]);
const isCookieVisible = ref(false);
const isAliTokenVisible = ref(false);
const isTransferModuleEnhancementLocked = ref(true);
const config = reactive({
  language: "zh_CN",
  enabled: false,
  notify: false,
  strm_url_format: 'pickcode',
  link_redirect_mode: 'cookie',
  cookies: '',
  aliyundrive_token: '',
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
  full_sync_remove_unless_dir: false,
  full_sync_remove_unless_file: false,
  full_sync_auto_download_mediainfo_enabled: false,
  full_sync_strm_log: true,
  full_sync_batch_num: 5000,
  full_sync_process_num: 128,
  cron_full_sync_strm: '0 */7 * * *',
  full_sync_strm_paths: '',
  full_sync_iter_function: 'iter_files_with_path_skim',
  full_sync_min_file_size: 0,
  increment_sync_strm_enabled: false,
  increment_sync_auto_download_mediainfo_enabled: false,
  increment_sync_cron: "0 * * * *",
  increment_sync_strm_paths: '',
  increment_sync_mp_mediaserver_paths: '',
  increment_sync_scrape_metadata_enabled: false,
  increment_sync_scrape_metadata_exclude_paths: '',
  increment_sync_media_server_refresh_enabled: false,
  increment_sync_mediaservers: [],
  increment_sync_min_file_size: 0,
  monitor_life_enabled: false,
  monitor_life_auto_download_mediainfo_enabled: false,
  monitor_life_paths: '',
  monitor_life_mp_mediaserver_paths: '',
  monitor_life_media_server_refresh_enabled: false,
  monitor_life_mediaservers: [],
  monitor_life_event_modes: [],
  monitor_life_scrape_metadata_enabled: false,
  monitor_life_scrape_metadata_exclude_paths: '',
  monitor_life_remove_mp_history: false,
  monitor_life_remove_mp_source: false,
  monitor_life_min_file_size: 0,
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
  pan_transfer_unrecognized_path: '',
  directory_upload_enabled: false,
  directory_upload_mode: 'compatibility',
  directory_upload_uploadext: 'mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v',
  directory_upload_copyext: 'srt,ssa,ass',
  directory_upload_path: [],
  nullbr_app_id: '',
  nullbr_api_key: '',
  tg_search_channels: [],
  same_playback: false,
  error_info_upload: false,
  upload_module_enhancement: false,
  upload_module_skip_slow_upload: false,
  upload_module_notify: true,
  upload_module_wait_time: 300,
  upload_module_wait_timeout: 3600,
  upload_module_skip_upload_wait_size: 0,
  upload_module_force_upload_wait_size: 0,
  upload_share_info: true,
  upload_offline_info: true,
  transfer_module_enhancement: false,
  strm_url_mode_custom: '',
  strm_generate_blacklist: [],
  mediainfo_download_whitelist: [],
  mediainfo_download_blacklist: [],
  strm_url_encode: false
});

// 消息提示
const message = reactive({
  text: '',
  type: 'info'
});

const skipUploadWaitSizeFormatted = computed({
  get() {
    if (!config.upload_module_skip_upload_wait_size || config.upload_module_skip_upload_wait_size <= 0) {
      return '';
    }
    return formatBytes(config.upload_module_skip_upload_wait_size);
  },
  set(newValue) {
    config.upload_module_skip_upload_wait_size = parseSize(newValue);
  },
});

const forceUploadWaitSizeFormatted = computed({
  get() {
    if (!config.upload_module_force_upload_wait_size || config.upload_module_force_upload_wait_size <= 0) {
      return '';
    }
    return formatBytes(config.upload_module_force_upload_wait_size);
  },
  set(newValue) {
    config.upload_module_force_upload_wait_size = parseSize(newValue);
  },
});

const fullSyncMinFileSizeFormatted = computed({
  get() {
    if (!config.full_sync_min_file_size || config.full_sync_min_file_size <= 0) {
      return '';
    }
    return formatBytes(config.full_sync_min_file_size);
  },
  set(newValue) {
    config.full_sync_min_file_size = parseSize(newValue);
  },
});

const incrementSyncMinFileSizeFormatted = computed({
  get() {
    if (!config.increment_sync_min_file_size || config.increment_sync_min_file_size <= 0) {
      return '';
    }
    return formatBytes(config.increment_sync_min_file_size);
  },
  set(newValue) {
    config.increment_sync_min_file_size = parseSize(newValue);
  },
});

const monitorLifeMinFileSizeFormatted = computed({
  get() {
    if (!config.monitor_life_min_file_size || config.monitor_life_min_file_size <= 0) {
      return '';
    }
    return formatBytes(config.monitor_life_min_file_size);
  },
  set(newValue) {
    config.monitor_life_min_file_size = parseSize(newValue);
  },
});

const parseSize = (sizeString) => {
  if (!sizeString || typeof sizeString !== 'string') return 0;
  const regex = /^(\d*\.?\d+)\s*(k|m|g|t)?b?$/i;
  const match = sizeString.trim().match(regex);
  if (!match) return 0;
  const num = parseFloat(match[1]);
  const unit = (match[2] || '').toLowerCase();
  switch (unit) {
    case 't': return Math.round(num * 1024 * 1024 * 1024 * 1024);
    case 'g': return Math.round(num * 1024 * 1024 * 1024);
    case 'm': return Math.round(num * 1024 * 1024);
    case 'k': return Math.round(num * 1024);
    default: return Math.round(num);
  }
};

const formatBytes = (bytes, decimals = 2) => {
  if (!+bytes) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'K', 'M', 'G', 'T'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const formattedNum = parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
  return `${formattedNum} ${sizes[i]}`;
};

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
const machineId = ref('');
const tgChannels = ref([{ name: '', id: '' }]);

const addTgChannel = () => {
  tgChannels.value.push({ name: '', id: '' });
};

const removeTgChannel = (index) => {
  tgChannels.value.splice(index, 1);
  if (tgChannels.value.length === 0) {
    tgChannels.value.push({ name: '', id: '' });
  }
};

const importDialog = reactive({
  show: false,
  jsonText: '',
  error: ''
});

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
  sign: "",
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

// 阿里云盘二维码登录对话框
const aliQrDialog = reactive({
  show: false,
  loading: false,
  error: null,
  qrcode: '',
  t: '',
  ck: '',
  status: '等待扫码',
  checkIntervalId: null,
});

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

// 监听 full_sync_remove_unless_strm 变化，当禁用时自动禁用依赖的配置项
watch(() => config.full_sync_remove_unless_strm, (newVal) => {
  if (!newVal) {
    // 当主配置被禁用时，自动禁用依赖的配置项
    config.full_sync_remove_unless_dir = false;
    config.full_sync_remove_unless_file = false;
  }
});

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

const checkTransferModuleEnhancement = async () => {
  try {
    const result = await props.api.get(`plugin/${PLUGIN_ID}/check_feature?name=transfer_module_enhancement`);
    if (result && result.enabled === true) {
      isTransferModuleEnhancementLocked.value = false;
    } else {
      isTransferModuleEnhancementLocked.value = true;
      config.transfer_module_enhancement = false;
    }
  } catch (err) {
    isTransferModuleEnhancementLocked.value = true;
    config.transfer_module_enhancement = false;
    console.error('检查 "整理模块增强" 功能授权失败:', err);
  }
};

// 加载配置
const loadConfig = async () => {
  try {
    loading.value = true;
    const data = await props.api.get(`plugin/${PLUGIN_ID}/get_config`);
    if (data) {
      Object.assign(config, data);
      directoryUploadPaths.value = (Array.isArray(config.directory_upload_path) && config.directory_upload_path.length > 0)
        ? JSON.parse(JSON.stringify(config.directory_upload_path))
        : [{ src: '', dest_remote: '', dest_local: '', delete: false }];
      let parsedChannels = [];
      if (config.tg_search_channels) {
        if (Array.isArray(config.tg_search_channels)) {
          parsedChannels = config.tg_search_channels;
        }
        else if (typeof config.tg_search_channels === 'string') {
          try {
            parsedChannels = JSON.parse(config.tg_search_channels);
          } catch (e) {
            console.error('解析旧的TG频道配置字符串失败:', e);
            parsedChannels = [];
          }
        }
      }
      if (Array.isArray(parsedChannels) && parsedChannels.length > 0) {
        tgChannels.value = parsedChannels;
      } else {
        tgChannels.value = [{ name: '', id: '' }];
      }
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
    config.transfer_monitor_paths = generatePathsConfig(transferPaths.value, 'transfer');
    config.transfer_mp_mediaserver_paths = generatePathsConfig(transferMpPaths.value, 'mp');
    config.full_sync_strm_paths = generatePathsConfig(fullSyncPaths.value, 'fullSync');
    config.increment_sync_strm_paths = generatePathsConfig(incrementSyncPaths.value, 'incrementSync');
    config.increment_sync_mp_mediaserver_paths = generatePathsConfig(incrementSyncMPPaths.value, 'increment-mp');
    config.monitor_life_paths = generatePathsConfig(monitorLifePaths.value, 'monitorLife');
    config.monitor_life_mp_mediaserver_paths = generatePathsConfig(monitorLifeMpPaths.value, 'monitorLifeMp');
    config.pan_transfer_paths = generatePathsConfig(panTransferPaths.value, 'panTransfer');
    config.directory_upload_path = directoryUploadPaths.value.filter(p => p.src?.trim() || p.dest_remote?.trim() || p.dest_local?.trim());
    const validChannels = tgChannels.value.filter(
      c => c.name && c.name.trim() !== '' && c.id && c.id.trim() !== ''
    );
    config.tg_search_channels = validChannels;
    emit('save', JSON.parse(JSON.stringify(config)));
    message.text = '配置已发送保存请求，请稍候...';
    message.type = 'info';
  } catch (err) {
    console.error('发送保存事件时出错:', err);
    message.text = `发送保存请求时出错: ${err.message || '未知错误'}`;
    message.type = 'error';
  } finally {
    saveLoading.value = false;
    setTimeout(() => {
      if (message.type === 'info' || message.type === 'error') {
        message.text = '';
      }
    }, 5000);
  }
};

const getMachineId = async () => {
  machineId.value = '正在获取...';
  try {
    const result = await props.api.get(`plugin/${PLUGIN_ID}/get_machine_id`);
    if (result && result.machine_id) {
      machineId.value = result.machine_id;
      message.text = '设备ID获取成功！';
      message.type = 'success';
    } else {
      throw new Error(result?.msg || '未能获取设备ID');
    }
  } catch (err) {
    machineId.value = '获取失败，请重试';
    message.text = `获取设备ID失败: ${err.message || '未知错误'}`;
    message.type = 'error';
  }
  setTimeout(() => {
    if (message.type === 'success' || message.type === 'info') {
      message.text = '';
    }
  }, 3000);
};

const handleConfirmFullSync = async () => {
  fullSyncConfirmDialog.value = false;
  await triggerFullSync();
};

const triggerFullSync = async () => {
  syncLoading.value = true;
  message.text = '';
  try {
    if (!config.enabled) throw new Error('插件未启用，请先启用插件');
    if (!config.cookies || config.cookies.trim() === '') throw new Error('请先设置115 Cookie');
    config.full_sync_strm_paths = generatePathsConfig(fullSyncPaths.value, 'fullSync');
    if (!config.full_sync_strm_paths) throw new Error('请先配置全量同步路径');

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

const triggerShareSync = async () => {
  shareSyncLoading.value = true;
  message.text = '';
  try {
    if (!config.enabled) throw new Error('插件未启用，请先启用插件');
    if (!config.cookies || config.cookies.trim() === '') throw new Error('请先设置115 Cookie');
    if (!config.share_target_path || config.share_target_path.trim() === '') throw new Error('请先配置分享目标路径');
    if (!config.share_strm_path || config.share_strm_path.trim() === '') throw new Error('请先配置分享STRM路径');

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

// 清理文件路径ID缓存
const clearIdPathCache = async () => {
  clearIdPathCacheLoading.value = true;
  message.text = '';
  try {
    const result = await props.api.post(`plugin/${PLUGIN_ID}/clear_id_path_cache`);
    if (result && result.code === 0) {
      message.text = result.msg || '文件路径ID缓存清理成功';
      message.type = 'success';
    } else {
      throw new Error(result?.msg || '文件路径ID缓存清理失败');
    }
  } catch (err) {
    message.text = `文件路径ID缓存清理失败: ${err.message || '未知错误'}`;
    message.type = 'error';
    console.error('文件路径ID缓存清理失败:', err);
  } finally {
    clearIdPathCacheLoading.value = false;
    setTimeout(() => {
      if (message.type === 'success' || message.type === 'error') {
        message.text = '';
      }
    }, 3000);
  }
};

// 清理增量同步跳过路径缓存
const clearIncrementSkipCache = async () => {
  clearIncrementSkipCacheLoading.value = true;
  message.text = '';
  try {
    const result = await props.api.post(`plugin/${PLUGIN_ID}/clear_increment_skip_cache`);
    if (result && result.code === 0) {
      message.text = result.msg || '增量同步跳过路径缓存清理成功';
      message.type = 'success';
    } else {
      throw new Error(result?.msg || '增量同步跳过路径缓存清理失败');
    }
  } catch (err) {
    message.text = `增量同步跳过路径缓存清理失败: ${err.message || '未知错误'}`;
    message.type = 'error';
    console.error('增量同步跳过路径缓存清理失败:', err);
  } finally {
    clearIncrementSkipCacheLoading.value = false;
    setTimeout(() => {
      if (message.type === 'success' || message.type === 'error') {
        message.text = '';
      }
    }, 3000);
  }
};

const addPath = (type) => {
  switch (type) {
    case 'transfer': transferPaths.value.push({ local: '', remote: '' }); break;
    case 'mp': transferMpPaths.value.push({ local: '', remote: '' }); break;
    case 'fullSync': fullSyncPaths.value.push({ local: '', remote: '' }); break;
    case 'incrementSync': incrementSyncPaths.value.push({ local: '', remote: '' }); break;
    case 'increment-mp': incrementSyncMPPaths.value.push({ local: '', remote: '' }); break;
    case 'monitorLife': monitorLifePaths.value.push({ local: '', remote: '' }); break;
    case 'monitorLifeMp': monitorLifeMpPaths.value.push({ local: '', remote: '' }); break;
    case 'directoryUpload': directoryUploadPaths.value.push({ src: '', dest_remote: '', dest_local: '', delete: false }); break;
  }
};
const removePath = (index, type) => {
  switch (type) {
    case 'transfer':
      transferPaths.value.splice(index, 1);
      if (transferPaths.value.length === 0) transferPaths.value = [{ local: '', remote: '' }];
      break;
    case 'mp':
      transferMpPaths.value.splice(index, 1);
      if (transferMpPaths.value.length === 0) transferMpPaths.value = [{ local: '', remote: '' }];
      break;
    case 'fullSync':
      fullSyncPaths.value.splice(index, 1);
      if (fullSyncPaths.value.length === 0) fullSyncPaths.value = [{ local: '', remote: '' }];
      break;
    case 'incrementSync':
      incrementSyncPaths.value.splice(index, 1);
      if (incrementSyncPaths.value.length === 0) incrementSyncPaths.value = [{ local: '', remote: '' }];
      break;
    case 'increment-mp':
      incrementSyncMPPaths.value.splice(index, 1);
      if (incrementSyncMPPaths.value.length === 0) incrementSyncMPPaths.value = [{ local: '', remote: '' }];
      break;
    case 'monitorLife':
      monitorLifePaths.value.splice(index, 1);
      if (monitorLifePaths.value.length === 0) monitorLifePaths.value = [{ local: '', remote: '' }];
      break;
    case 'monitorLifeMp':
      monitorLifeMpPaths.value.splice(index, 1);
      if (monitorLifeMpPaths.value.length === 0) monitorLifeMpPaths.value = [{ local: '', remote: '' }];
      break;
    case 'directoryUpload':
      directoryUploadPaths.value.splice(index, 1);
      if (directoryUploadPaths.value.length === 0) directoryUploadPaths.value = [{ src: '', dest_remote: '', dest_local: '', delete: false }];
      break;
  }
};
const addPanTransferPath = () => { panTransferPaths.value.push({ path: '' }); };
const removePanTransferPath = (index) => {
  panTransferPaths.value.splice(index, 1);
  if (panTransferPaths.value.length === 0) panTransferPaths.value = [{ path: '' }];
};

const openImportDialog = () => {
  importDialog.jsonText = '';
  importDialog.error = '';
  importDialog.show = true;
};
const closeImportDialog = () => {
  importDialog.show = false;
};
const handleConfirmImport = () => {
  importDialog.error = '';
  if (!importDialog.jsonText || !importDialog.jsonText.trim()) {
    importDialog.error = '输入内容不能为空。';
    return;
  }
  try {
    const parsedData = JSON.parse(importDialog.jsonText);
    if (!Array.isArray(parsedData)) throw new Error("数据必须是一个数组。");
    const isValidStructure = parsedData.every(
      item => typeof item === 'object' && item !== null && 'name' in item && 'id' in item
    );
    if (!isValidStructure) throw new Error("数组中的每个元素都必须是包含 'name' 和 'id' 键的对象。");
    tgChannels.value = parsedData.length > 0 ? parsedData : [{ name: '', id: '' }];
    message.text = '频道配置导入成功！';
    message.type = 'success';
    closeImportDialog();
  } catch (e) {
    importDialog.error = `导入失败: ${e.message}`;
    console.error("频道导入解析失败:", e);
  }
};

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
  dirDialog.currentPath = '/';
  loadDirContent();
};

const loadDirContent = async () => {
  dirDialog.loading = true;
  dirDialog.error = null;
  dirDialog.items = [];
  try {
    if (dirDialog.isLocal) {
      try {
        const response = await props.api.post('storage/list', { path: dirDialog.currentPath || '/', type: 'share', flag: 'ROOT' });
        if (response && Array.isArray(response)) {
          dirDialog.items = response
            .filter(item => item.type === 'dir')
            .map(item => ({ name: item.name, path: item.path, is_dir: true }))
            .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
        } else {
          throw new Error('浏览目录失败：无效响应');
        }
      } catch (error) {
        console.error('浏览本地目录失败:', error);
        dirDialog.error = `浏览本地目录失败: ${error.message || '未知错误'}`;
        dirDialog.items = [];
      }
    } else {
      if (!config.cookies || config.cookies.trim() === '') {
        throw new Error('请先设置115 Cookie才能浏览网盘目录');
      }
      const result = await props.api.get(`plugin/${PLUGIN_ID}/browse_dir?path=${encodeURIComponent(dirDialog.currentPath)}&is_local=${dirDialog.isLocal}`);

      if (result && result.code === 0 && result.data) {
        dirDialog.items = result.data.items
          .filter(item => item.is_dir)
          .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));
        dirDialog.currentPath = result.data.path || dirDialog.currentPath;
      } else {
        throw new Error(result?.msg || '获取网盘目录内容失败');
      }
    }
  } catch (error) {
    console.error('加载目录内容失败:', error);
    dirDialog.error = error.message || '获取目录内容失败';
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
  if (!dirDialog.isLocal) {
    if (path === '/') return;
    let current = path.replace(/\\/g, '/');
    if (current.length > 1 && current.endsWith('/')) current = current.slice(0, -1);
    const parent = current.substring(0, current.lastIndexOf('/'));
    dirDialog.currentPath = parent === '' ? '/' : parent;
    loadDirContent();
    return;
  }
  if (path === '/' || path === 'C:\\' || path === 'C:/') return;
  const normalizedPath = path.replace(/\\/g, '/');
  const parts = normalizedPath.split('/').filter(Boolean);
  if (parts.length === 0) {
    dirDialog.currentPath = '/';
  } else if (parts.length === 1 && normalizedPath.includes(':')) {
    dirDialog.currentPath = parts[0] + ':/';
  } else {
    parts.pop();
    dirDialog.currentPath = parts.length === 0 ? '/' : (normalizedPath.startsWith('/') ? '/' : '') + parts.join('/') + '/';
  }
  loadDirContent();
};
const confirmDirSelection = () => {
  if (!dirDialog.currentPath) return;
  let processedPath = dirDialog.currentPath;
  if (processedPath !== '/' && !(/^[a-zA-Z]:[\\\/]$/.test(processedPath)) && (processedPath.endsWith('/') || processedPath.endsWith('\\\\'))) {
    processedPath = processedPath.slice(0, -1);
  }
  if (dirDialog.type === 'excludePath' && dirDialog.targetConfigKeyForExclusion) {
    const targetKey = dirDialog.targetConfigKeyForExclusion;
    let targetArrayRef;
    if (targetKey === 'transfer_monitor_scrape_metadata_exclude_paths') targetArrayRef = transferExcludePaths;
    else if (targetKey === 'monitor_life_scrape_metadata_exclude_paths') targetArrayRef = monitorLifeExcludePaths;
    else if (targetKey === 'increment_sync_scrape_metadata_exclude_paths') targetArrayRef = incrementSyncExcludePaths;
    if (targetArrayRef) {
      if (targetArrayRef.value.length === 1 && !targetArrayRef.value[0].path) {
        targetArrayRef.value[0] = { path: processedPath };
      } else {
        if (!targetArrayRef.value.some(item => item.path === processedPath)) {
          targetArrayRef.value.push({ path: processedPath });
        } else {
          message.text = '该排除路径已存在。';
          message.type = 'warning';
          setTimeout(() => { message.text = ''; }, 3000);
        }
      }
    }
    dirDialog.type = dirDialog.originalPathTypeBackup;
    dirDialog.index = dirDialog.originalIndexBackup;
    dirDialog.targetConfigKeyForExclusion = null;
    dirDialog.originalPathTypeBackup = '';
    dirDialog.originalIndexBackup = -1;
  }
  else if (dirDialog.index >= 0 && dirDialog.type !== 'excludePath') {
    switch (dirDialog.type) {
      case 'transfer': dirDialog.isLocal ? transferPaths.value[dirDialog.index].local = processedPath : transferPaths.value[dirDialog.index].remote = processedPath; break;
      case 'fullSync': dirDialog.isLocal ? fullSyncPaths.value[dirDialog.index].local = processedPath : fullSyncPaths.value[dirDialog.index].remote = processedPath; break;
      case 'incrementSync': dirDialog.isLocal ? incrementSyncPaths.value[dirDialog.index].local = processedPath : incrementSyncPaths.value[dirDialog.index].remote = processedPath; break;
      case 'monitorLife': dirDialog.isLocal ? monitorLifePaths.value[dirDialog.index].local = processedPath : monitorLifePaths.value[dirDialog.index].remote = processedPath; break;
      case 'panTransfer': panTransferPaths.value[dirDialog.index].path = processedPath; break;
      case 'directoryUpload':
        if (dirDialog.fieldKey && directoryUploadPaths.value[dirDialog.index]) directoryUploadPaths.value[dirDialog.index][dirDialog.fieldKey] = processedPath;
        break;
    }
  }
  else if (dirDialog.type === 'panTransferUnrecognized') config.pan_transfer_unrecognized_path = processedPath;
  else if (dirDialog.type === 'sharePath') dirDialog.isLocal ? config.user_share_local_path = processedPath : config.user_share_pan_path = processedPath;
  closeDirDialog();
};
const closeDirDialog = () => {
  dirDialog.show = false;
  dirDialog.items = [];
  dirDialog.error = null;
};

const copyCookieToClipboard = async () => {
  if (!config.cookies) { message.text = 'Cookie为空，无法复制。'; message.type = 'warning'; return; }
  try {
    await navigator.clipboard.writeText(config.cookies);
    message.text = 'Cookie已复制到剪贴板！';
    message.type = 'success';
  } catch (err) {
    console.error('复制Cookie失败:', err);
    message.text = '复制Cookie失败。请检查浏览器权限或确保通过HTTPS访问，或尝试手动复制。';
    message.type = 'error';
  }
  setTimeout(() => { if (message.type === 'success' || message.type === 'warning' || message.type === 'error') message.text = ''; }, 3000);
};
const copyAliTokenToClipboard = async () => {
  if (!config.aliyundrive_token) { message.text = 'Token为空，无法复制。'; message.type = 'warning'; return; }
  try {
    await navigator.clipboard.writeText(config.aliyundrive_token);
    message.text = '阿里云盘Token已复制到剪贴板！';
    message.type = 'success';
  } catch (err) {
    console.error('复制Token失败:', err);
    message.text = '复制Token失败。请检查浏览器权限或手动复制。';
    message.type = 'error';
  }
  setTimeout(() => { message.text = ''; }, 3000);
};

const openQrCodeDialog = () => {
  qrDialog.show = true;
  qrDialog.loading = false;
  qrDialog.error = null;
  qrDialog.qrcode = '';
  qrDialog.uid = '';
  qrDialog.time = '';
  qrDialog.sign = '';
  if (!clientTypes.some(ct => ct.value === qrDialog.clientType)) qrDialog.clientType = 'alipaymini';
  const selectedClient = clientTypes.find(type => type.value === qrDialog.clientType);
  qrDialog.tips = selectedClient ? `请使用${selectedClient.label}扫描二维码登录` : '请使用支付宝扫描二维码登录';
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
  console.warn(`【115STRM助手 DEBUG】准备获取二维码，前端选择的 clientType: ${qrDialog.clientType}`);
  try {
    const response = await props.api.get(`plugin/${PLUGIN_ID}/get_qrcode?client_type=${qrDialog.clientType}`);
    if (response && response.code === 0 && response.data) {
      qrDialog.uid = response.data.uid;
      qrDialog.time = response.data.time;
      qrDialog.sign = response.data.sign;
      qrDialog.qrcode = response.data.qrcode;
      qrDialog.tips = response.data.tips || '请扫描二维码登录';
      qrDialog.status = '等待扫码';
      if (response.data.client_type) qrDialog.clientType = response.data.client_type;
      startQrCodeCheckInterval();
    } else {
      qrDialog.error = response?.msg || '获取二维码失败';
      console.error("【115STRM助手 DEBUG】获取二维码API调用失败或返回错误码: ", response);
    }
  } catch (err) {
    qrDialog.error = `获取二维码出错: ${err.message || '未知错误'}`;
    console.error('【115STRM助手 DEBUG】获取二维码 JS 捕获异常:', err);
  } finally {
    qrDialog.loading = false;
  }
};

const checkQrCodeStatus = async () => {
  if (!qrDialog.uid || !qrDialog.show || !qrDialog.time || !qrDialog.sign) return;
  try {
    const response = await props.api.get(`plugin/${PLUGIN_ID}/check_qrcode?uid=${qrDialog.uid}&time=${qrDialog.time}&sign=${qrDialog.sign}&client_type=${qrDialog.clientType}`);
    if (response && response.code === 0 && response.data) {
      const data = response.data;
      if (data.status === 'waiting') qrDialog.status = '等待扫码';
      else if (data.status === 'scanned') qrDialog.status = '已扫码，请在设备上确认';
      else if (data.status === 'success') {
        if (data.cookie) {
          clearQrCodeCheckInterval();
          qrDialog.status = '登录成功！';
          config.cookies = data.cookie;
          message.text = '登录成功！Cookie已获取，请点击下方"保存配置"按钮保存。';
          message.type = 'success';
          setTimeout(() => { qrDialog.show = false; }, 3000);
        } else {
          qrDialog.status = '登录似乎成功，但未获取到Cookie';
          message.text = '登录成功但未获取到Cookie信息，请重试或检查账号。';
          message.type = 'warning';
          clearQrCodeCheckInterval();
        }
      }
    } else if (response) {
      if (qrDialog.status !== '登录成功，正在处理...') {
        clearQrCodeCheckInterval();
        qrDialog.error = response.msg || '二维码已失效，请刷新';
        qrDialog.status = '二维码已失效';
      }
    }
  } catch (err) {
    if (qrDialog.status !== '登录成功，正在处理...') console.error('检查二维码状态JS捕获异常:', err);
  }
};

const startQrCodeCheckInterval = () => {
  clearQrCodeCheckInterval();
  qrDialog.checkIntervalId = setInterval(checkQrCodeStatus, 3000);
};

const openAliQrCodeDialog = () => {
  aliQrDialog.show = true;
  aliQrDialog.loading = false;
  aliQrDialog.error = null;
  aliQrDialog.qrcode = '';
  aliQrDialog.t = '';
  aliQrDialog.ck = '';
  aliQrDialog.status = '等待扫码';
  getAliQrCode();
};

const getAliQrCode = async () => {
  aliQrDialog.loading = true;
  aliQrDialog.error = null;
  aliQrDialog.qrcode = '';
  try {
    const response = await props.api.get(`plugin/${PLUGIN_ID}/get_aliyundrive_qrcode`);
    if (response && response.code === 0 && response.data) {
      aliQrDialog.qrcode = response.data.qrcode;
      aliQrDialog.t = response.data.t;
      aliQrDialog.ck = response.data.ck;
      aliQrDialog.status = '等待扫码';
      startAliQrCodeCheckInterval();
    } else {
      aliQrDialog.error = response?.msg || '获取阿里云盘二维码失败';
    }
  } catch (err) {
    aliQrDialog.error = `获取二维码出错: ${err.message || '未知错误'}`;
  } finally {
    aliQrDialog.loading = false;
  }
};

const checkAliQrCodeStatus = async () => {
  if (!aliQrDialog.t || !aliQrDialog.ck || !aliQrDialog.show) return;
  try {
    const response = await props.api.get(`plugin/${PLUGIN_ID}/check_aliyundrive_qrcode?t=${aliQrDialog.t}&ck=${encodeURIComponent(aliQrDialog.ck)}`);
    if (response && response.code === 0 && response.data) {
      if (response.data.status === 'success' && response.data.token) {
        clearAliQrCodeCheckInterval();
        aliQrDialog.status = '登录成功！';
        config.aliyundrive_token = response.data.token;
        message.text = '阿里云盘登录成功！Token已获取，请点击下方“保存配置”按钮。';
        message.type = 'success';
        setTimeout(() => { aliQrDialog.show = false; }, 2000);
      } else {
        aliQrDialog.status = response.data.msg || '等待扫码';
        if (response.data.status === 'expired' || response.data.status === 'invalid') {
          clearAliQrCodeCheckInterval();
          aliQrDialog.error = '二维码已失效，请刷新';
        }
      }
    } else if (response) {
      clearAliQrCodeCheckInterval();
      aliQrDialog.status = '二维码已失效';
      aliQrDialog.error = response.msg || '二维码检查失败，请刷新。';
    }
  } catch (err) {
    console.error('检查阿里云盘二维码状态出错:', err);
  }
};

const startAliQrCodeCheckInterval = () => {
  clearAliQrCodeCheckInterval();
  aliQrDialog.checkIntervalId = setInterval(checkAliQrCodeStatus, 2000);
};
const clearAliQrCodeCheckInterval = () => {
  if (aliQrDialog.checkIntervalId) {
    clearInterval(aliQrDialog.checkIntervalId);
    aliQrDialog.checkIntervalId = null;
  }
};
const refreshAliQrCode = () => {
  clearAliQrCodeCheckInterval();
  aliQrDialog.error = null;
  getAliQrCode();
};
const closeAliQrCodeDialog = () => {
  clearAliQrCodeCheckInterval();
  aliQrDialog.show = false;
};

const clearQrCodeCheckInterval = () => {
  if (qrDialog.checkIntervalId) {
    clearInterval(qrDialog.checkIntervalId);
    qrDialog.checkIntervalId = null;
  }
};
const refreshQrCode = () => {
  clearQrCodeCheckInterval();
  qrDialog.error = null;
  const matchedType = clientTypes.find(type => type.value === qrDialog.clientType);
  qrDialog.tips = matchedType ? `请使用${matchedType.label}扫描二维码登录` : '请扫描二维码登录';
  getQrCode();
};
const closeQrDialog = () => {
  clearQrCodeCheckInterval();
  qrDialog.show = false;
};

onMounted(async () => {
  await loadConfig();
  await checkTransferModuleEnhancement();
});

onBeforeUnmount(() => {
  console.log('组件即将卸载，清理定时器...');
  clearQrCodeCheckInterval();
  clearAliQrCodeCheckInterval();
});

watch(() => qrDialog.clientType, (newVal, oldVal) => {
  if (newVal !== oldVal && qrDialog.show) {
    console.log(`【115STRM助手 DEBUG】qrDialog.clientType 从 ${oldVal} 变为 ${newVal}，准备刷新二维码`);
    refreshQrCode();
  }
});

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

const openExcludeDirSelector = (configKeyToUpdate) => {
  dirDialog.show = true;
  dirDialog.isLocal = true;
  dirDialog.loading = false;
  dirDialog.error = null;
  dirDialog.items = [];
  dirDialog.currentPath = '/';
  dirDialog.originalPathTypeBackup = dirDialog.type;
  dirDialog.originalIndexBackup = dirDialog.index;
  dirDialog.targetConfigKeyForExclusion = configKeyToUpdate;
  dirDialog.type = 'excludePath';
  dirDialog.index = -1;
  loadDirContent();
};

const removeExcludePathEntry = (index, type) => {
  let targetArrayRef;
  if (type === 'transfer_exclude') targetArrayRef = transferExcludePaths;
  else if (type === 'life_exclude') targetArrayRef = monitorLifeExcludePaths;
  else if (type === 'increment_exclude') targetArrayRef = incrementSyncExcludePaths;
  if (targetArrayRef && targetArrayRef.value && index < targetArrayRef.value.length) {
    targetArrayRef.value.splice(index, 1);
    if (targetArrayRef.value.length === 0) targetArrayRef.value = [{ path: '' }];
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

/* 缓存卡片响应式样式 */
.cache-card {
  min-height: 200px;
}

/* 移动端优化 */
@media (max-width: 959px) {
  .cache-card {
    min-height: auto;
    height: auto;
  }
}

/* 桌面端保持固定高度 */
@media (min-width: 960px) {
  .cache-card {
    height: 200px;
  }
}
</style>
