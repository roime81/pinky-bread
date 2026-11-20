FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /opt/pinky-bread-companion
COPY package.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund
RUN mkdir -p /data
EXPOSE 3020
CMD ["npm", "start"]
