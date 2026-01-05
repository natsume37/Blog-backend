#!/usr/bin/env python3
"""
创建用户账号脚本 (完全交互式输入 & 简化循环 & 支持退出)

使用方法:
    cd backend
    uv run python scripts/create_admin.py

    在任何输入提示符下，输入 'q' 或 'quit' 即可退出脚本。
"""

import sys
import os
import re
from sqlalchemy import or_

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 尝试导入依赖项
try:
    from app.core.database import SessionLocal, engine, Base
    from app.core.security import get_password_hash
    from app.models.user import User
except ImportError as e:
    print(f"❌ 依赖导入失败，请确保您在项目根目录运行，并且依赖已安装。")
    print(f"   错误信息: {e}")
    sys.exit(1)


# --- 核心逻辑 ---

def create_or_update_user(
        username: str,
        email: str,
        password: str,
        nickname: str = None,
        is_admin: bool = False
) -> bool:
    """创建或更新用户账号"""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 检查用户是否存在 (用户名或邮箱)
        user = db.query(User).filter(or_(User.username == username, User.email == email)).first()

        if user:
            print(f"\n⚠️  检测到已存在用户: {user.username} (邮箱: {user.email})")
            print(f"    当前身份: {'管理员' if user.is_admin else '普通用户'}")
            
            # 如果是管理员脚本，通常有权限重置密码
            confirm = get_validated_input(
                "❓ 是否重置该用户的密码？(y/n)",
                validate_yes_no,
                allow_empty=False
            ).lower()

            if confirm == 'y':
                user.hashed_password = get_password_hash(password)
                # 如果提供了新昵称，则更新
                if nickname:
                    user.nickname = nickname
                
                # 如果要求是管理员，强制更新权限
                if is_admin and not user.is_admin:
                    user.is_admin = True
                    print("    已升级为管理员权限")
                
                db.commit()
                print(f"✅ 用户 {user.username} 密码已重置！")
                return True
            else:
                print("🚫 操作已取消，未修改任何信息。")
                return False

        # 创建新用户
        new_user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            nickname=nickname if nickname else username,
            is_active=True,
            is_admin=is_admin
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        user_type = "管理员" if is_admin else "普通用户"

        print("\n" + "=" * 50)
        print(f"✅ {user_type} 账号创建成功!")
        print(f"   用户名: {username}")
        print(f"   邮箱: {email}")
        print(f"   昵称: {new_user.nickname}")
        print(f"   ID: {new_user.id}")
        print("=" * 50 + "\n")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n❌ 操作失败: {e}")
        return False
    finally:
        db.close()


# --- 校验函数（保持不变） ---

def validate_username(username: str) -> bool:
    """校验用户名，要求非空且长度适中"""
    if not username:
        print("🚨 用户名不能为空。")
        return False
    if len(username) < 3 or len(username) > 20:
        print("🚨 用户名长度应在 3 到 20 个字符之间。")
        return False
    return True


def validate_email(email: str) -> bool:
    """校验邮箱格式"""
    if not email:
        print("🚨 邮箱不能为空。")
        return False
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        print("🚨 请输入有效的邮箱地址格式（例如: user@example.com）。")
        return False
    return True


def validate_password(password: str) -> bool:
    """校验密码强度，要求长度至少6位"""
    if not password:
        print("🚨 密码不能为空。")
        return False
    if len(password) < 6:
        print("🚨 密码长度至少需要 6 位。")
        return False
    return True


def validate_yes_no(choice: str) -> bool:
    """校验是/否输入"""
    if choice not in ['y', 'n']:
        print("🚨 输入无效，请键入 'y' 或 'n'。")
        return False
    return True


# --- 通用输入获取函数 (核心优化) ---

def get_validated_input(prompt: str, validator, allow_empty: bool = False, optional_default: str = None):
    """
    通用输入获取函数。

    :param prompt: 输入提示。
    :param validator: 校验函数（返回 bool）。
    :param allow_empty: 是否允许空输入。
    :param optional_default: 允许空输入时，如果用户回车，使用的默认值。
    :return: 有效输入字符串或 None (如果用户选择退出)。
    """
    while True:
        # 构建更友好的提示
        full_prompt = prompt
        if optional_default:
            full_prompt += f" [默认: {optional_default}]"
        full_prompt += " (q/quit 退出): "

        user_input = input(full_prompt).strip()

        # 检查退出命令
        if user_input.lower() in ['q', 'quit']:
            print("\n👋 退出脚本。")
            sys.exit(0)

        # 处理可选输入和默认值
        if not user_input:
            if allow_empty:
                return optional_default if optional_default is not None else user_input
            else:
                print("🚨 输入不能为空。请重新输入。")
                continue  # 继续循环，要求输入

        # 校验输入
        if validator(user_input):
            return user_input

        # 如果校验失败，validator 函数内部会打印错误信息，然后循环继续


def interactive_mode():
    """完全交互式创建用户，使用通用函数简化流程"""
    print("=" * 60)
    print("          ✨ 博客用户账号创建向导 ✨")
    print("      请根据提示，逐行输入账户信息 (输入 q 随时退出)")
    print("=" * 60)
    print()

    # 1. 获取用户名
    # validator 必须接受一个参数 (输入值)
    username = get_validated_input(
        "1. 请输入用户名 (3-20个字符)",
        validate_username,
        allow_empty=False
    )
    if username is None: return  # 不会执行到这里，因为 get_validated_input 在退出时会 sys.exit(0)

    # 2. 获取邮箱
    email = get_validated_input(
        "2. 请输入邮箱 (例如: user@domain.com)",
        validate_email,
        allow_empty=False
    )

    # 3. 获取密码
    password = get_validated_input(
        "3. 请输入密码 (至少6位)",
        validate_password,
        allow_empty=False
    )

    # 4. 获取昵称（可选）
    nickname = get_validated_input(
        f"4. 请输入昵称 (可选，回车默认为用户名/不修改原昵称)",
        lambda x: True,  # 对昵称的输入不进行格式校验，总是通过
        allow_empty=True,
        optional_default=None
    )

    # 5. 询问是否为管理员
    is_admin_choice = get_validated_input(
        "5. 是否将此用户设置为管理员? (y/n)",
        validate_yes_no,
        allow_empty=False
    ).lower()

    is_admin = (is_admin_choice == 'y')

    # --- 最终确认 ---
    print("\n" + "-" * 30)
    print("✅ 账号信息最终确认:")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")
    # 昵称可能为空，但 get_validated_input 已经处理了默认值
    print(f"  昵称: {nickname if nickname else username}")
    print(f"  身份: {'管理员' if is_admin else '普通用户'}")
    print("-" * 30)

    # 6. 最终创建
    confirm = get_validated_input(
        "确认创建此用户账号? (y/n)",
        validate_yes_no,
        allow_empty=False
    ).lower()

    if confirm == 'y':
        create_or_update_user(username, email, password, nickname, is_admin)
    else:
        print("\n🚀 操作已取消。")


def main():
    print("脚本启动，即将进入交互式用户创建流程...")
    # 使用 try-finally 块以确保即使在退出时也能进行清理（尽管 sys.exit 可能会跳过）
    try:
        interactive_mode()
    except Exception as e:
        print(f"\n发生未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()