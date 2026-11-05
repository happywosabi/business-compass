# 前端镜像：先用 Node 把网页打包成静态文件，再放进 Nginx。服务器上不需要安装 Node。

# ---- 第一阶段：打包 ----
FROM node:22-alpine AS build
WORKDIR /app

# 下载慢时可以指定国内镜像源，例如：
#   docker compose build --build-arg NPM_REGISTRY=https://registry.npmmirror.com nginx
ARG NPM_REGISTRY=https://registry.npmjs.org

# 先只复制依赖清单并安装：代码变动时可以复用这一层缓存，构建更快
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --registry="${NPM_REGISTRY}"

COPY . .
# 打包前先做类型检查，有错误时构建直接失败，不会把有问题的版本发布出去
RUN npm run build

# ---- 第二阶段：只保留打包结果 ----
FROM nginx:1.28-alpine
COPY --from=build /app/dist /usr/share/nginx/html
