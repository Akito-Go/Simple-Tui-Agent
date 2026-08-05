#!/usr/bin/env python3
"""俄罗斯方块小游戏 - 使用 Pygame 实现"""

import pygame
import random
import sys

# ====== 字体检测 ======
def get_chinese_font(size):
    """自动检测系统中可用的中文字体"""
    pygame.font.init()
    # 获取系统中所有可用字体名（小写）
    available_fonts = [f.lower() for f in pygame.font.get_fonts()]

    # 按优先级排列的中文字体关键词
    font_keywords = [
        "stheitimedium", "stheitilight",     # macOS 华文黑体
        "hiraginosansgb",                     # macOS 冬青黑体
        "applesdgothicneo",                   # macOS
        "simhei", "simsun",                   # Windows
        "microsoftyahei",                     # Windows
        "notosanscjk", "notosanssc",          # Linux
        "wenquanyimicrohei", "wqymicrohei",   # Linux
        "droidfallback",                      # Android/Linux
        "notosans",                           # Linux 通用
        "notoserif",                          # Linux 通用
        "sourcehan", "source han",            # 思源
        "fangsong", "kaiti",                  # 其他中文字体
        "stkaiti", "stfangso",
    ]

    # 在可用字体中匹配关键词
    matched = []
    for kw in font_keywords:
        for af in available_fonts:
            if kw in af:
                matched.append(af)

    # 去重并保留顺序
    seen = set()
    unique_matched = []
    for m in matched:
        if m not in seen:
            seen.add(m)
            unique_matched.append(m)

    # 尝试使用匹配到的字体
    for font_name in unique_matched:
        try:
            font = pygame.font.SysFont(font_name, size)
            test_surf = font.render("测试", True, (255, 255, 255))
            # 中文渲染宽度应明显大于英文"测试"的回退宽度
            if test_surf.get_width() > size * 1.5:  # 至少能渲染出字符
                return font
        except Exception:
            continue

    # 回退：让 pygame 自动选一个字体
    try:
        font = pygame.font.Font(None, size)
        return font
    except Exception:
        return pygame.font.Font(None, size)


# 颜色定义
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
ORANGE = (255, 165, 0)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 0)
PURPLE = (128, 0, 128)
RED = (255, 0, 0)

# 游戏设置
BLOCK_SIZE = 30
COLS = 10
ROWS = 20
PANEL_WIDTH = 200
WINDOW_WIDTH = COLS * BLOCK_SIZE + PANEL_WIDTH
WINDOW_HEIGHT = ROWS * BLOCK_SIZE
FPS = 60

# 方块形状定义
SHAPES = [
    # I
    [[1, 1, 1, 1]],
    # O
    [[1, 1],
     [1, 1]],
    # T
    [[0, 1, 0],
     [1, 1, 1]],
    # S
    [[0, 1, 1],
     [1, 1, 0]],
    # Z
    [[1, 1, 0],
     [0, 1, 1]],
    # J
    [[1, 0, 0],
     [1, 1, 1]],
    # L
    [[0, 0, 1],
     [1, 1, 1]],
]

SHAPE_COLORS = [CYAN, YELLOW, PURPLE, GREEN, RED, BLUE, ORANGE]


class Tetris:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Tetris")
        self.clock = pygame.time.Clock()
        self.font = get_chinese_font(24)
        self.big_font = get_chinese_font(48)
        self.reset_game()

    def reset_game(self):
        """重置游戏"""
        self.board = [[0] * COLS for _ in range(ROWS)]
        self.score = 0
        self.level = 1
        self.lines_cleared = 0
        self.game_over = False
        self.paused = False
        self.drop_speed = 500  # 毫秒
        self.last_drop_time = pygame.time.get_ticks()
        self.current_piece = self.new_piece()
        self.next_piece = self.new_piece()

    def new_piece(self):
        """生成新方块"""
        shape_idx = random.randint(0, len(SHAPES) - 1)
        shape = [row[:] for row in SHAPES[shape_idx]]
        color = SHAPE_COLORS[shape_idx]
        return {
            "shape": shape,
            "color": color,
            "x": COLS // 2 - len(shape[0]) // 2,
            "y": 0,
        }

    def rotate_piece(self, piece):
        """旋转方块"""
        shape = piece["shape"]
        rows = len(shape)
        cols = len(shape[0])
        rotated = [[shape[rows - 1 - j][i] for j in range(rows)] for i in range(cols)]
        return rotated

    def valid_move(self, piece, dx=0, dy=0, new_shape=None):
        """检查移动是否有效"""
        shape = new_shape if new_shape else piece["shape"]
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    new_x = piece["x"] + x + dx
                    new_y = piece["y"] + y + dy
                    if new_x < 0 or new_x >= COLS or new_y >= ROWS:
                        return False
                    if new_y >= 0 and self.board[new_y][new_x]:
                        return False
        return True

    def lock_piece(self):
        """固定当前方块到面板"""
        piece = self.current_piece
        for y, row in enumerate(piece["shape"]):
            for x, cell in enumerate(row):
                if cell:
                    board_y = piece["y"] + y
                    board_x = piece["x"] + x
                    if board_y >= 0:
                        self.board[board_y][board_x] = piece["color"]
        self.clear_lines()
        self.current_piece = self.next_piece
        self.next_piece = self.new_piece()
        if not self.valid_move(self.current_piece):
            self.game_over = True

    def clear_lines(self):
        """消除满行并更新分数"""
        full_lines = []
        for y in range(ROWS):
            if all(self.board[y]):
                full_lines.append(y)

        if full_lines:
            for y in full_lines:
                del self.board[y]
                self.board.insert(0, [0] * COLS)

            cleared = len(full_lines)
            self.lines_cleared += cleared
            # 计分规则：1行100, 2行300, 3行500, 4行800
            points = [0, 100, 300, 500, 800]
            self.score += points[cleared] * self.level
            self.level = self.lines_cleared // 10 + 1
            self.drop_speed = max(100, 500 - (self.level - 1) * 40)

    def drop_hard(self):
        """硬降 - 直接落到底"""
        while self.valid_move(self.current_piece, dy=1):
            self.current_piece["y"] += 1
        self.lock_piece()

    def get_ghost_y(self):
        """获取幽灵方块（预览落点）的 y 坐标"""
        ghost_y = self.current_piece["y"]
        while self.valid_move(self.current_piece, dy=ghost_y - self.current_piece["y"] + 1):
            ghost_y += 1
        return ghost_y

    def draw_block(self, x, y, color, alpha=255):
        """绘制一个方块"""
        rect = pygame.Rect(x, y, BLOCK_SIZE - 1, BLOCK_SIZE - 1)
        if alpha < 255:
            s = pygame.Surface((BLOCK_SIZE - 1, BLOCK_SIZE - 1), pygame.SRCALPHA)
            s.fill((*color, alpha))
            self.screen.blit(s, (x, y))
        else:
            pygame.draw.rect(self.screen, color, rect)
        # 边框高光效果
        if alpha == 255:
            inner_rect = pygame.Rect(x + 2, y + 2, BLOCK_SIZE - 5, BLOCK_SIZE - 5)
            lighter = tuple(min(255, c + 60) for c in color)
            pygame.draw.rect(self.screen, lighter, inner_rect, 1)

    def draw_board(self):
        """绘制游戏面板"""
        for y in range(ROWS):
            for x in range(COLS):
                if self.board[y][x]:
                    self.draw_block(
                        x * BLOCK_SIZE, y * BLOCK_SIZE, self.board[y][x]
                    )

        # 绘制网格线
        for x in range(COLS + 1):
            pygame.draw.line(
                self.screen, GRAY,
                (x * BLOCK_SIZE, 0), (x * BLOCK_SIZE, WINDOW_HEIGHT), 1
            )
        for y in range(ROWS + 1):
            pygame.draw.line(
                self.screen, GRAY,
                (0, y * BLOCK_SIZE), (COLS * BLOCK_SIZE, y * BLOCK_SIZE), 1
            )

    def draw_piece(self, piece, offset_x=0, offset_y=0, alpha=255):
        """绘制方块"""
        for y, row in enumerate(piece["shape"]):
            for x, cell in enumerate(row):
                if cell:
                    self.draw_block(
                        (piece["x"] + x + offset_x) * BLOCK_SIZE,
                        (piece["y"] + y + offset_y) * BLOCK_SIZE,
                        piece["color"],
                        alpha,
                    )

    def draw_ghost(self):
        """绘制幽灵方块（预览落点）"""
        ghost_y = self.get_ghost_y()
        for y, row in enumerate(self.current_piece["shape"]):
            for x, cell in enumerate(row):
                if cell:
                    rect = pygame.Rect(
                        (self.current_piece["x"] + x) * BLOCK_SIZE,
                        (ghost_y + y) * BLOCK_SIZE,
                        BLOCK_SIZE - 1,
                        BLOCK_SIZE - 1,
                    )
                    pygame.draw.rect(self.screen, GRAY, rect, 2)

    def draw_panel(self):
        """绘制右侧信息面板"""
        panel_x = COLS * BLOCK_SIZE + 20

        # 标题
        title = self.font.render("俄罗斯方块", True, WHITE)
        self.screen.blit(title, (panel_x, 20))

        # 下一个方块
        label = self.font.render("下一个:", True, WHITE)
        self.screen.blit(label, (panel_x, 70))

        next_piece = self.next_piece
        for y, row in enumerate(next_piece["shape"]):
            for x, cell in enumerate(row):
                if cell:
                    self.draw_block(
                        panel_x + x * BLOCK_SIZE,
                        110 + y * BLOCK_SIZE,
                        next_piece["color"],
                    )

        # 分数
        score_label = self.font.render("分数:", True, WHITE)
        self.screen.blit(score_label, (panel_x, 230))
        score_text = self.font.render(str(self.score), True, YELLOW)
        self.screen.blit(score_text, (panel_x, 260))

        # 等级
        level_label = self.font.render("等级:", True, WHITE)
        self.screen.blit(level_label, (panel_x, 300))
        level_text = self.font.render(str(self.level), True, YELLOW)
        self.screen.blit(level_text, (panel_x, 330))

        # 消除行数
        lines_label = self.font.render("消除行:", True, WHITE)
        self.screen.blit(lines_label, (panel_x, 370))
        lines_text = self.font.render(str(self.lines_cleared), True, YELLOW)
        self.screen.blit(lines_text, (panel_x, 400))

        # 操作提示
        controls = [
            "操作:",
            "← → 移动",
            "↑ 旋转",
            "↓ 加速下落",
            "空格 硬降",
            "P 暂停/继续",
            "R 重新开始",
            "ESC 退出游戏",
        ]
        y_offset = 460
        for line in controls:
            text = self.font.render(line, True, WHITE)
            self.screen.blit(text, (panel_x, y_offset))
            y_offset += 30

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

                if event.key == pygame.K_LEFT:
                    if self.valid_move(self.current_piece, dx=-1):
                        self.current_piece["x"] -= 1
                elif event.key == pygame.K_RIGHT:
                    if self.valid_move(self.current_piece, dx=1):
                        self.current_piece["x"] += 1
                elif event.key == pygame.K_DOWN:
                    if self.valid_move(self.current_piece, dy=1):
                        self.current_piece["y"] += 1
                        self.score += 1  # 软降加分
                elif event.key == pygame.K_UP:
                    rotated = self.rotate_piece(self.current_piece)
                    if self.valid_move(self.current_piece, new_shape=rotated):
                        self.current_piece["shape"] = rotated
                elif event.key == pygame.K_SPACE:
                    self.drop_hard()

        return True

    def update(self):
        """更新游戏状态"""
        if self.game_over or self.paused:
            return

        now = pygame.time.get_ticks()
        if now - self.last_drop_time > self.drop_speed:
            if self.valid_move(self.current_piece, dy=1):
                self.current_piece["y"] += 1
            else:
                self.lock_piece()
            self.last_drop_time = now

    def draw(self):
        """绘制画面"""
        self.screen.fill(BLACK)

        # 绘制游戏面板
        self.draw_board()

        # 绘制幽灵方块
        if not self.game_over:
            self.draw_ghost()

        # 绘制当前方块
        if not self.game_over:
            self.draw_piece(self.current_piece)

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
    game = Tetris()
    game.run()


if __name__ == "__main__":
    main()
