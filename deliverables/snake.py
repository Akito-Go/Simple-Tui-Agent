#!/usr/bin/env python3
"""贪吃蛇小游戏 - 使用 Pygame 实现"""

import pygame
import random
import sys

# ====== 字体检测 ======
def get_chinese_font(size):
    """自动检测系统中可用的中文字体"""
    pygame.font.init()
    available_fonts = [f.lower() for f in pygame.font.get_fonts()]

    font_keywords = [
        "stheitimedium", "stheitilight",
        "hiraginosansgb",
        "applesdgothicneo",
        "simhei", "simsun",
        "microsoftyahei",
        "notosanscjk", "notosanssc",
        "wenquanyimicrohei", "wqymicrohei",
        "droidfallback",
        "notosans",
        "notoserif",
        "sourcehan", "source han",
        "fangsong", "kaiti",
        "stkaiti", "stfangso",
    ]

    matched = []
    for kw in font_keywords:
        for af in available_fonts:
            if kw in af:
                matched.append(af)

    seen = set()
    unique_matched = []
    for m in matched:
        if m not in seen:
            seen.add(m)
            unique_matched.append(m)

    for font_name in unique_matched:
        try:
            font = pygame.font.SysFont(font_name, size)
            test_surf = font.render("测试", True, (255, 255, 255))
            if test_surf.get_width() > size * 1.5:
                return font
        except Exception:
            continue

    try:
        font = pygame.font.Font(None, size)
        return font
    except Exception:
        return pygame.font.Font(None, size)


# 颜色定义
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
DARK_GRAY = (40, 40, 40)
GREEN = (0, 200, 0)
DARK_GREEN = (0, 150, 0)
RED = (255, 50, 50)
YELLOW = (255, 255, 0)
BLUE = (50, 150, 255)
ORANGE = (255, 165, 0)

# 游戏设置
BLOCK_SIZE = 25
COLS = 20
ROWS = 20
PANEL_WIDTH = 200
WINDOW_WIDTH = COLS * BLOCK_SIZE + PANEL_WIDTH
WINDOW_HEIGHT = ROWS * BLOCK_SIZE
FPS = 10

# 方向常量
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)


class Snake:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("贪吃蛇")
        self.clock = pygame.time.Clock()
        self.font = get_chinese_font(22)
        self.big_font = get_chinese_font(48)
        self.small_font = get_chinese_font(16)
        self.reset_game()

    def reset_game(self):
        """重置游戏"""
        # 蛇：列表中的每个元素是 (x, y) 坐标
        center_x, center_y = COLS // 2, ROWS // 2
        self.snake = [
            (center_x, center_y),
            (center_x - 1, center_y),
            (center_x - 2, center_y),
        ]
        self.direction = RIGHT
        self.next_direction = RIGHT
        self.score = 0
        self.level = 1
        self.game_over = False
        self.paused = False
        self.food = self.spawn_food()
        self.speed = FPS
        self.last_move_time = pygame.time.get_ticks()
        self.move_interval = 150  # 毫秒

    def spawn_food(self):
        """生成食物，确保不在蛇身上"""
        while True:
            food = (
                random.randint(0, COLS - 1),
                random.randint(0, ROWS - 1),
            )
            if food not in self.snake:
                return food

    def handle_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and self.game_over:
                    self.reset_game()
                    return True

                if event.key == pygame.K_p:
                    self.paused = not self.paused
                    return True

                if self.game_over or self.paused:
                    return True

                # 方向控制（不能反向）
                if event.key == pygame.K_UP and self.direction != DOWN:
                    self.next_direction = UP
                elif event.key == pygame.K_DOWN and self.direction != UP:
                    self.next_direction = DOWN
                elif event.key == pygame.K_LEFT and self.direction != RIGHT:
                    self.next_direction = LEFT
                elif event.key == pygame.K_RIGHT and self.direction != LEFT:
                    self.next_direction = RIGHT

        return True

    def update(self):
        """更新游戏状态"""
        if self.game_over or self.paused:
            return

        now = pygame.time.get_ticks()
        if now - self.last_move_time < self.move_interval:
            return
        self.last_move_time = now

        # 应用方向
        self.direction = self.next_direction

        # 计算新头部位置
        head = self.snake[0]
        new_head = (
            head[0] + self.direction[0],
            head[1] + self.direction[1],
        )

        # 检查是否吃到食物
        ate_food = new_head == self.food

        # 插入新头部
        self.snake.insert(0, new_head)

        if ate_food:
            self.score += 10 * self.level
            self.food = self.spawn_food()
            # 每吃 5 个食物升一级
            if self.score // (10 * self.level) % 5 == 0:
                self.level = min(self.level + 1, 10)
                self.move_interval = max(50, 150 - (self.level - 1) * 10)
        else:
            self.snake.pop()

        # 碰撞检测
        head = self.snake[0]
        # 撞墙
        if head[0] < 0 or head[0] >= COLS or head[1] < 0 or head[1] >= ROWS:
            self.game_over = True
        # 撞自己（排除头部自身）
        if head in self.snake[1:]:
            self.game_over = True

    def draw_block(self, x, y, color, size=None):
        """绘制一个方块"""
        s = size or BLOCK_SIZE
        rect = pygame.Rect(x, y, s - 1, s - 1)
        pygame.draw.rect(self.screen, color, rect)
        # 高光效果
        lighter = tuple(min(255, c + 40) for c in color)
        inner_rect = pygame.Rect(x + 2, y + 2, s - 5, s - 5)
        pygame.draw.rect(self.screen, lighter, inner_rect, 1)

    def draw_grid(self):
        """绘制网格"""
        for x in range(COLS + 1):
            pygame.draw.line(
                self.screen, DARK_GRAY,
                (x * BLOCK_SIZE, 0), (x * BLOCK_SIZE, WINDOW_HEIGHT), 1
            )
        for y in range(ROWS + 1):
            pygame.draw.line(
                self.screen, DARK_GRAY,
                (0, y * BLOCK_SIZE), (COLS * BLOCK_SIZE, y * BLOCK_SIZE), 1
            )

    def draw_snake(self):
        """绘制蛇"""
        for i, segment in enumerate(self.snake):
            x, y = segment
            if i == 0:
                # 蛇头
                self.draw_block(x * BLOCK_SIZE, y * BLOCK_SIZE, GREEN)
                # 眼睛
                eye_size = 4
                eye_offset = BLOCK_SIZE // 4
                for ex, ey in [(-1, -1), (1, -1)]:
                    if self.direction == UP:
                        dx, dy = 0, -eye_offset
                    elif self.direction == DOWN:
                        dx, dy = 0, eye_offset
                    elif self.direction == LEFT:
                        dx, dy = -eye_offset, 0
                    else:
                        dx, dy = eye_offset, 0
                    eye_x = x * BLOCK_SIZE + BLOCK_SIZE // 2 + dx - eye_size // 2
                    eye_y = y * BLOCK_SIZE + BLOCK_SIZE // 2 + dy - eye_size // 2
                    pygame.draw.circle(self.screen, WHITE, (eye_x, eye_y), eye_size)
                    pygame.draw.circle(self.screen, BLACK, (eye_x, eye_y), eye_size // 2)
            else:
                # 蛇身：渐变颜色
                ratio = 1.0 - (i / len(self.snake)) * 0.5
                color = (
                    int(0 * ratio),
                    int(200 * ratio),
                    int(0 * ratio),
                )
                self.draw_block(x * BLOCK_SIZE, y * BLOCK_SIZE, color)

    def draw_food(self):
        """绘制食物"""
        x, y = self.food
        cx = x * BLOCK_SIZE + BLOCK_SIZE // 2
        cy = y * BLOCK_SIZE + BLOCK_SIZE // 2
        radius = BLOCK_SIZE // 2 - 2
        # 发光效果
        for r in range(radius, radius - 3, -1):
            alpha = 255 - (radius - r) * 60
            color = (255, max(0, 50 - (radius - r) * 20), max(0, 50 - (radius - r) * 20))
            pygame.draw.circle(self.screen, color, (cx, cy), r)
        pygame.draw.circle(self.screen, RED, (cx, cy), radius)

    def draw_panel(self):
        """绘制右侧信息面板"""
        panel_x = COLS * BLOCK_SIZE + 20

        # 标题
        title = self.font.render("贪吃蛇", True, WHITE)
        self.screen.blit(title, (panel_x, 20))

        # 分数
        score_label = self.font.render("分数:", True, WHITE)
        self.screen.blit(score_label, (panel_x, 80))
        score_text = self.font.render(str(self.score), True, YELLOW)
        self.screen.blit(score_text, (panel_x, 110))

        # 等级
        level_label = self.font.render("等级:", True, WHITE)
        self.screen.blit(level_label, (panel_x, 160))
        level_text = self.font.render(str(self.level), True, YELLOW)
        self.screen.blit(level_text, (panel_x, 190))

        # 蛇长
        length_label = self.font.render("蛇长:", True, WHITE)
        self.screen.blit(length_label, (panel_x, 240))
        length_text = self.font.render(str(len(self.snake)), True, YELLOW)
        self.screen.blit(length_text, (panel_x, 270))

        # 操作提示
        controls = [
            "操作:",
            "↑ ↓ ← → 移动",
            "P 暂停/继续",
            "R 重新开始",
            "ESC 退出游戏",
        ]
        y_offset = 340
        for line in controls:
            text = self.small_font.render(line, True, WHITE)
            self.screen.blit(text, (panel_x, y_offset))
            y_offset += 28

    def draw_game_over(self):
        """绘制游戏结束画面"""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        game_over_text = self.big_font.render("游戏结束", True, RED)
        text_rect = game_over_text.get_rect(
            center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40)
        )
        self.screen.blit(game_over_text, text_rect)

        score_text = self.font.render(f"最终得分: {self.score}", True, WHITE)
        score_rect = score_text.get_rect(
            center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 20)
        )
        self.screen.blit(score_text, score_rect)

        restart_text = self.font.render("按 R 重新开始", True, WHITE)
        restart_rect = restart_text.get_rect(
            center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 60)
        )
        self.screen.blit(restart_text, restart_rect)

    def draw_pause(self):
        """绘制暂停画面"""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pause_text = self.big_font.render("暂停", True, WHITE)
        text_rect = pause_text.get_rect(
            center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        )
        self.screen.blit(pause_text, text_rect)

    def draw(self):
        """绘制画面"""
        self.screen.fill(BLACK)

        # 绘制游戏区域
        self.draw_grid()
        self.draw_food()
        self.draw_snake()

        # 绘制右侧面板
        self.draw_panel()

        # 绘制分隔线
        pygame.draw.line(
            self.screen, WHITE,
            (COLS * BLOCK_SIZE, 0), (COLS * BLOCK_SIZE, WINDOW_HEIGHT), 2
        )

        # 绘制暂停/结束画面
        if self.game_over:
            self.draw_game_over()
        elif self.paused:
            self.draw_pause()

        pygame.display.flip()

    def run(self):
        """主循环"""
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


def main():
    game = Snake()
    game.run()


if __name__ == "__main__":
    main()
