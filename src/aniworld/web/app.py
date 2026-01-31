"""
Flask web application for AniWorld Downloader
"""

import logging
import os
import time
import threading
import webbrowser
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, jsonify, request, session, redirect, url_for

from .. import config
from .database import UserDatabase
from .download_manager import get_download_manager


class WebApp:
    """Flask web application wrapper for AniWorld Downloader"""

    def __init__(self, host="127.0.0.1", port=5000, debug=False, arguments=None):
        """
        Initialize the Flask web application.

        Args:
            host: Host to bind to (default: 127.0.0.1)
            port: Port to bind to (default: 5000)
            debug: Enable Flask debug mode (default: False)
            arguments: Command line arguments object
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.arguments = arguments
        self.start_time = time.time()

        # Authentication settings
        self.auth_enabled = (
            getattr(arguments, "enable_web_auth", False) if arguments else False
        )
        # Always initialize database for sync jobs functionality
        self.db = UserDatabase()

        # Download manager
        self.download_manager = get_download_manager(self.db)

        # Sync manager
        from .sync_manager import get_sync_manager
        self.sync_manager = get_sync_manager(self.db, self.download_manager) if self.db else None
        if self.sync_manager:
            self.sync_manager.start()

        # Create Flask app
        self.app = self._create_app()

        # Setup routes
        self._setup_routes()

    def _create_app(self) -> Flask:
        """Create and configure Flask application."""
        # Get the web module directory
        web_dir = os.path.dirname(os.path.abspath(__file__))

        app = Flask(
            __name__,
            template_folder=os.path.join(web_dir, "templates"),
            static_folder=os.path.join(web_dir, "static"),
        )

        # Configure Flask
        app.config["SECRET_KEY"] = os.urandom(24)
        app.config["JSON_SORT_KEYS"] = False

        return app

    def _require_api_auth(self, f):
        """Decorator to require authentication for API routes."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.auth_enabled:
                return f(*args, **kwargs)

            if not self.db:
                return jsonify({"error": "Authentication database not available"}), 500

            session_token = request.cookies.get("session_token")
            if not session_token:
                return jsonify({"error": "Authentication required"}), 401

            user = self.db.get_user_by_session(session_token)
            if not user:
                return jsonify({"error": "Invalid session"}), 401

            return f(*args, **kwargs)

        return decorated_function

    def _require_auth(self, f):
        """Decorator to require authentication for routes."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.auth_enabled:
                return f(*args, **kwargs)

            if not self.db:
                return redirect(url_for("login"))

            # Check for session token in cookies
            session_token = request.cookies.get("session_token")
            if not session_token:
                return redirect(url_for("login"))

            user = self.db.get_user_by_session(session_token)
            if not user:
                return redirect(url_for("login"))

            # Store user info in Flask session for templates
            session["user"] = user
            return f(*args, **kwargs)

        return decorated_function

    def _require_admin(self, f):
        """Decorator to require admin privileges for routes."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.auth_enabled:
                return f(*args, **kwargs)

            if not self.db:
                return jsonify({"error": "Authentication database not available"}), 500

            session_token = request.cookies.get("session_token")
            if not session_token:
                return redirect(url_for("login"))

            user = self.db.get_user_by_session(session_token)
            if not user or not user["is_admin"]:
                return jsonify({"error": "Admin access required"}), 403

            session["user"] = user
            return f(*args, **kwargs)

        return decorated_function

    def _setup_routes(self):
        """Setup Flask routes."""

        @self.app.route("/")
        @self._require_auth
        def index():
            """Main page route."""
            if self.auth_enabled and self.db:
                # Check if this is first-time setup
                if not self.db.has_users():
                    return redirect(url_for("setup"))

                # Get current user info for template
                session_token = request.cookies.get("session_token")
                user = self.db.get_user_by_session(session_token)
                return render_template("index.html", user=user, auth_enabled=True)
            else:
                return render_template("index.html", auth_enabled=False)

        @self.app.route("/login", methods=["GET", "POST"])
        def login():
            """Login page route."""
            if not self.auth_enabled or not self.db:
                return redirect(url_for("index"))

            # If no users exist, redirect to setup
            if not self.db.has_users():
                return redirect(url_for("setup"))

            if request.method == "POST":
                data = request.get_json()
                username = data.get("username", "").strip()
                password = data.get("password", "")

                if not username or not password:
                    return jsonify(
                        {"success": False, "error": "Username and password required"}
                    ), 400

                user = self.db.verify_user(username, password)
                if user:
                    session_token = self.db.create_session(user["id"])
                    response = jsonify({"success": True, "redirect": url_for("index")})
                    response.set_cookie(
                        "session_token",
                        session_token,
                        httponly=True,
                        secure=False,
                        max_age=30 * 24 * 60 * 60,
                    )
                    return response
                else:
                    return jsonify(
                        {"success": False, "error": "Invalid credentials"}
                    ), 401

            return render_template("login.html")

        @self.app.route("/logout", methods=["POST"])
        def logout():
            """Logout route."""
            if not self.auth_enabled or not self.db:
                return redirect(url_for("index"))

            session_token = request.cookies.get("session_token")
            if session_token:
                self.db.delete_session(session_token)

            response = jsonify({"success": True, "redirect": url_for("login")})
            response.set_cookie("session_token", "", expires=0)
            return response

        @self.app.route("/setup", methods=["GET", "POST"])
        def setup():
            """First-time setup route for creating admin user."""
            if not self.auth_enabled or not self.db:
                return redirect(url_for("index"))

            if self.db.has_users():
                return redirect(url_for("index"))

            if request.method == "POST":
                data = request.get_json()
                username = data.get("username", "").strip()
                password = data.get("password", "")

                if not username or not password:
                    return jsonify(
                        {"success": False, "error": "Username and password required"}
                    ), 400

                if len(password) < 6:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Password must be at least 6 characters",
                        }
                    ), 400

                if self.db.create_user(
                    username, password, is_admin=True, is_original_admin=True
                ):
                    return jsonify(
                        {
                            "success": True,
                            "message": "Admin user created successfully",
                            "redirect": url_for("login"),
                        }
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Failed to create user"}
                    ), 500

            return render_template("setup.html")

        @self.app.route("/settings")
        @self._require_auth
        def settings():
            """Settings page route."""
            if not self.auth_enabled or not self.db:
                return redirect(url_for("index"))

            session_token = request.cookies.get("session_token")
            user = self.db.get_user_by_session(session_token)
            users = self.db.get_all_users() if user and user["is_admin"] else []

            return render_template("settings.html", user=user, users=users)

        # User management API routes
        @self.app.route("/api/users", methods=["GET"])
        @self._require_admin
        def api_get_users():
            """Get all users (admin only)."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Authentication not available"}
                ), 500
            users = self.db.get_all_users()
            return jsonify({"success": True, "users": users})

        @self.app.route("/api/users", methods=["POST"])
        @self._require_admin
        def api_create_user():
            """Create new user (admin only)."""
            data = request.get_json()

            if not data:
                return jsonify(
                    {"success": False, "error": "No JSON data received"}
                ), 400

            # Debug logging
            logging.debug(f"Received data: {data}")

            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            is_admin = data.get("is_admin", False)

            # Debug logging
            logging.debug(
                f"Processed - username: '{username}', password: 'XXX', is_admin: {is_admin}"
            )

            if not username or not password:
                return jsonify(
                    {
                        "success": False,
                        "error": f'Username and password required. Got username: "{username}", password: "{password}"',
                    }
                ), 400

            if len(password) < 6:
                return jsonify(
                    {
                        "success": False,
                        "error": "Password must be at least 6 characters",
                    }
                ), 400

            if not self.db:
                return jsonify(
                    {"success": False, "error": "Authentication not available"}
                ), 500

            if self.db.create_user(username, password, is_admin):
                return jsonify(
                    {"success": True, "message": "User created successfully"}
                )
            else:
                return jsonify(
                    {
                        "success": False,
                        "error": "Failed to create user (username may already exist)",
                    }
                ), 400

        @self.app.route("/api/users/<int:user_id>", methods=["DELETE"])
        @self._require_admin
        def api_delete_user(user_id):
            """Delete user (admin only)."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Authentication not available"}
                ), 500

            # Get user info to check if it's the original admin
            users = self.db.get_all_users()
            user_to_delete = next((u for u in users if u["id"] == user_id), None)

            if user_to_delete and user_to_delete.get("is_original_admin"):
                return jsonify(
                    {"success": False, "error": "Cannot delete the original admin user"}
                ), 400

            if self.db.delete_user(user_id):
                return jsonify(
                    {"success": True, "message": "User deleted successfully"}
                )
            else:
                return jsonify(
                    {"success": False, "error": "Failed to delete user"}
                ), 400

        @self.app.route("/api/users/<int:user_id>", methods=["PUT"])
        @self._require_admin
        def api_update_user(user_id):
            """Update user (admin only)."""
            data = request.get_json()
            username = (
                data.get("username", "").strip() if data.get("username") else None
            )
            password = data.get("password", "") if data.get("password") else None
            is_admin = data.get("is_admin") if "is_admin" in data else None

            if password and len(password) < 6:
                return jsonify(
                    {
                        "success": False,
                        "error": "Password must be at least 6 characters",
                    }
                ), 400

            if not self.db:
                return jsonify(
                    {"success": False, "error": "Authentication not available"}
                ), 500

            if self.db.update_user(user_id, username, password, is_admin):
                return jsonify(
                    {"success": True, "message": "User updated successfully"}
                )
            else:
                return jsonify(
                    {"success": False, "error": "Failed to update user"}
                ), 400

        @self.app.route("/api/change-password", methods=["POST"])
        @self._require_api_auth
        def api_change_password():
            """Change user password."""
            if not self.auth_enabled or not self.db:
                return jsonify(
                    {"success": False, "error": "Authentication not enabled"}
                ), 400

            session_token = request.cookies.get("session_token")
            user = self.db.get_user_by_session(session_token)
            if not user:
                return jsonify({"success": False, "error": "Invalid session"}), 401

            data = request.get_json()
            current_password = data.get("current_password", "")
            new_password = data.get("new_password", "")

            if not current_password or not new_password:
                return jsonify(
                    {
                        "success": False,
                        "error": "Current and new passwords are required",
                    }
                ), 400

            if len(new_password) < 6:
                return jsonify(
                    {
                        "success": False,
                        "error": "New password must be at least 6 characters",
                    }
                ), 400

            if self.db.change_password(user["id"], current_password, new_password):
                return jsonify(
                    {"success": True, "message": "Password changed successfully"}
                )
            else:
                return jsonify(
                    {
                        "success": False,
                        "error": "Failed to change password. Current password may be incorrect.",
                    }
                ), 400

        @self.app.route("/api/test")
        @self._require_api_auth
        def api_test():
            """API test endpoint."""
            return jsonify(
                {
                    "status": "success",
                    "message": "Connection test successful",
                    "timestamp": datetime.now().isoformat(),
                    "version": config.VERSION,
                }
            )

        @self.app.route("/api/info")
        @self._require_api_auth
        def api_info():
            """API info endpoint."""
            uptime_seconds = int(time.time() - self.start_time)
            uptime_str = self._format_uptime(uptime_seconds)

            # Convert latest_version to string if it's a Version object
            latest_version = getattr(config, "LATEST_VERSION", None)
            if latest_version is not None:
                latest_version = str(latest_version)

            return jsonify(
                {
                    "version": config.VERSION,
                    "status": "running",
                    "uptime": uptime_str,
                    "latest_version": latest_version,
                    "is_newest": getattr(config, "IS_NEWEST_VERSION", True),
                    "supported_providers": list(config.SUPPORTED_PROVIDERS),
                    "platform": config.PLATFORM_SYSTEM,
                }
            )

        @self.app.route("/health")
        def health():
            """Health check endpoint."""
            return jsonify(
                {"status": "healthy", "timestamp": datetime.now().isoformat()}
            )

        @self.app.route("/api/search", methods=["POST"])
        @self._require_api_auth
        def api_search():
            """Search for anime endpoint."""
            try:
                from flask import request

                data = request.get_json()
                if not data or "query" not in data:
                    return jsonify(
                        {"success": False, "error": "Query parameter is required"}
                    ), 400

                query = data["query"].strip()
                if not query:
                    return jsonify(
                        {"success": False, "error": "Query cannot be empty"}
                    ), 400

                # Get site parameter (default to both)
                site = data.get("site", "both")

                # Create wrapper function for search with dual-site support
                def search_anime_wrapper(keyword, site="both"):
                    """Wrapper function for anime search with multi-site support"""
                    from ..search import fetch_anime_list
                    from .. import config
                    from urllib.parse import quote

                    if site == "both":
                        # Search both sites using existing fetch_anime_list function
                        aniworld_url = f"{config.ANIWORLD_TO}/ajax/seriesSearch?keyword={quote(keyword)}"
                        sto_url = (
                            f"{config.S_TO}/ajax/seriesSearch?keyword={quote(keyword)}"
                        )

                        # Fetch from both sites
                        aniworld_results = []
                        sto_results = []

                        try:
                            aniworld_results = fetch_anime_list(aniworld_url)
                        except Exception as e:
                            logging.warning(f"Failed to fetch from aniworld: {e}")

                        try:
                            sto_results = fetch_anime_list(sto_url)
                        except Exception as e:
                            logging.warning(f"Failed to fetch from s.to: {e}")

                        # Combine and deduplicate results
                        all_results = []
                        seen_slugs = set()

                        # Add aniworld results first
                        for anime in aniworld_results:
                            slug = anime.get("link", "")
                            if slug and slug not in seen_slugs:
                                anime["site"] = "aniworld.to"
                                anime["base_url"] = config.ANIWORLD_TO
                                anime["stream_path"] = "anime/stream"
                                all_results.append(anime)
                                seen_slugs.add(slug)

                        # Add s.to results, but skip duplicates
                        for anime in sto_results:
                            slug = anime.get("link", "")
                            if slug and slug not in seen_slugs:
                                anime["site"] = "s.to"
                                anime["base_url"] = config.S_TO
                                anime["stream_path"] = "serie/stream"
                                all_results.append(anime)
                                seen_slugs.add(slug)

                        return all_results

                    elif site == "s.to":
                        # Single site search - s.to
                        search_url = (
                            f"{config.S_TO}/ajax/seriesSearch?keyword={quote(keyword)}"
                        )
                        try:
                            results = fetch_anime_list(search_url)
                            for anime in results:
                                anime["site"] = "s.to"
                                anime["base_url"] = config.S_TO
                                anime["stream_path"] = "serie/stream"
                            return results
                        except Exception as e:
                            logging.error(f"s.to search failed: {e}")
                            return []

                    else:
                        # Single site search - aniworld.to (default)
                        from ..search import search_anime

                        try:
                            results = search_anime(keyword=keyword, only_return=True)
                            for anime in results:
                                anime["site"] = "aniworld.to"
                                anime["base_url"] = config.ANIWORLD_TO
                                anime["stream_path"] = "anime/stream"
                            return results
                        except Exception as e:
                            logging.error(f"aniworld.to search failed: {e}")
                            return []

                # Use wrapper function
                results = search_anime_wrapper(query, site)

                # Process results - simplified without episode fetching
                processed_results = []
                for anime in results[:50]:  # Limit to 50 results
                    # Get the link and construct full URL if needed
                    link = anime.get("link", "")
                    anime_site = anime.get("site", "aniworld")
                    anime_base_url = anime.get("base_url", config.ANIWORLD_TO)
                    anime_stream_path = anime.get("stream_path", "anime/stream")

                    if link and not link.startswith("http"):
                        # If it's just a slug, construct the full URL using the anime's specific site info
                        full_url = f"{anime_base_url}/{anime_stream_path}/{link}"
                    else:
                        full_url = link

                    # Use the same field names as CLI search
                    name = anime.get("name", "Unknown Name")
                    year = anime.get("productionYear", "Unknown Year")

                    # Create title like CLI does, but avoid double parentheses
                    if year and year != "Unknown Year" and str(year) not in name:
                        title = f"{name} {year}"
                    else:
                        title = name

                    processed_anime = {
                        "title": title,
                        "url": full_url,
                        "description": anime.get("description", ""),
                        "slug": link,
                        "name": name,
                        "year": year,
                        "site": anime_site,
                        "cover": anime.get("cover", ""),
                    }

                    processed_results.append(processed_anime)

                return jsonify(
                    {
                        "success": True,
                        "results": processed_results,
                        "count": len(processed_results),
                    }
                )

            except Exception as err:
                logging.error(f"Search error: {err}")
                return jsonify(
                    {"success": False, "error": f"Search failed: {str(err)}"}
                ), 500

        @self.app.route("/api/download", methods=["POST"])
        @self._require_api_auth
        def api_download():
            """Start download endpoint."""
            try:
                from flask import request

                data = request.get_json()

                # Check for both single episode (legacy) and multiple episodes (new)
                episode_urls = data.get("episode_urls", [])
                single_episode_url = data.get("episode_url")

                if single_episode_url:
                    episode_urls = [single_episode_url]

                if not episode_urls:
                    return jsonify(
                        {"success": False, "error": "Episode URL(s) required"}
                    ), 400

                language = data.get("language", "German Sub")
                provider = data.get("provider", "VOE")
                custom_path = data.get("custom_path")
                if custom_path:
                    custom_path = custom_path.strip() or None
                else:
                    custom_path = None
                keep_updated = data.get("keep_updated", False)
                check_interval = data.get("check_interval", 24)
                series_url = data.get("series_url", "")

                # DEBUG: Log received parameters
                logging.debug(
                    f"WEB API RECEIVED - Language: '{language}', Provider: '{provider}'"
                )
                logging.debug(f"WEB API RECEIVED - Request data: {data}")

                # Get current user for queue tracking
                current_user = None
                if self.auth_enabled and self.db:
                    session_token = request.cookies.get("session_token")
                    current_user = self.db.get_user_by_session(session_token)

                # Determine anime title
                anime_title = data.get("anime_title", "Unknown Anime")

                # Calculate total episodes by checking episode URLs
                from ..entry import _group_episodes_by_series

                try:
                    anime_list = _group_episodes_by_series(episode_urls)
                    total_episodes = sum(
                        len(anime.episode_list) for anime in anime_list
                    )
                except Exception as e:
                    logging.error(f"Failed to process episode URLs: {e}")
                    return jsonify(
                        {
                            "success": False,
                            "error": "No valid anime objects could be created from provided URLs",
                        }
                    ), 400

                if total_episodes == 0:
                    return jsonify(
                        {
                            "success": False,
                            "error": "No valid anime objects could be created from provided URLs",
                        }
                    ), 400

                # Add to download queue
                queue_id = self.download_manager.add_download(
                    anime_title=anime_title,
                    episode_urls=episode_urls,
                    language=language,
                    provider=provider,
                    total_episodes=total_episodes,
                    created_by=current_user["id"] if current_user else None,
                    custom_path=custom_path,
                )

                if not queue_id:
                    return jsonify(
                        {"success": False, "error": "Failed to add download to queue"}
                    ), 500

                # Create sync job if keep_updated is enabled
                sync_job_id = None
                if keep_updated and series_url and self.db and self.sync_manager:
                    try:
                        sync_job_id = self.db.create_sync_job(
                            anime_title=anime_title,
                            series_url=series_url,
                            check_interval=check_interval,
                            language=language,
                            provider=provider,
                            custom_path=custom_path,
                            created_by=current_user["id"] if current_user else None,
                        )
                        logging.info(f"Created sync job {sync_job_id} for {anime_title}")
                    except Exception as e:
                        logging.error(f"Failed to create sync job: {e}")

                response_data = {
                    "success": True,
                    "message": f"Download added to queue: {total_episodes} episode(s)",
                    "episode_count": total_episodes,
                    "language": language,
                    "provider": provider,
                    "queue_id": queue_id,
                }

                if sync_job_id:
                    response_data["sync_job_id"] = sync_job_id
                    response_data["message"] += " (Auto-sync enabled)"

                return jsonify(response_data)

            except Exception as err:
                logging.error(f"Download error: {err}")
                return jsonify(
                    {"success": False, "error": f"Failed to start download: {str(err)}"}
                ), 500

        @self.app.route("/api/download-path")
        @self._require_api_auth
        def api_download_path():
            """Get download path endpoint."""
            try:
                # Use arguments.output_dir if available, otherwise fall back to default
                download_path = str(config.DEFAULT_DOWNLOAD_PATH)
                if (
                    self.arguments
                    and hasattr(self.arguments, "output_dir")
                    and self.arguments.output_dir is not None
                ):
                    download_path = str(self.arguments.output_dir)

                return jsonify({"path": download_path})
            except Exception as err:
                logging.error(f"Failed to get download path: {err}")
                return jsonify({"path": str(config.DEFAULT_DOWNLOAD_PATH)}), 500

        @self.app.route("/api/browse-directory", methods=["POST"])
        @self._require_api_auth
        def api_browse_directory():
            """Open a directory picker dialog on the server."""
            try:
                import tkinter as tk
                from tkinter import filedialog
                
                # Create hidden root window
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True) # Bring to front
                
                # Open dialog
                path = filedialog.askdirectory(title="Select Download Directory")
                root.destroy()
                
                if path:
                    # Normalize path separators
                    path = os.path.normpath(path)
                    return jsonify({"success": True, "path": path})
                else:
                    return jsonify({"success": False, "message": "No directory selected"})
                    
            except Exception as e:
                logging.error(f"Failed to open directory picker: {e}")
                return jsonify({"success": False, "error": f"Failed to open directory picker: {str(e)}"}), 500

        @self.app.route("/api/episodes", methods=["POST"])
        @self._require_api_auth
        def api_episodes():
            """Get episodes for a series endpoint."""
            try:
                from flask import request

                data = request.get_json()
                if not data or "series_url" not in data:
                    return jsonify(
                        {"success": False, "error": "Series URL is required"}
                    ), 400

                series_url = data["series_url"]

                # Create wrapper function to handle all logic
                def get_episodes_for_series(series_url):
                    """Wrapper function using existing functions to get episodes and movies"""
                    from ..common import (
                        get_season_episode_count,
                        get_movie_episode_count,
                    )
                    from ..entry import _detect_site_from_url
                    from .. import config

                    # Extract slug and site using existing functions
                    _site = _detect_site_from_url(series_url)

                    if "/anime/stream/" in series_url:
                        slug = series_url.split("/anime/stream/")[-1].rstrip("/")
                        stream_path = "anime/stream"
                        base_url = config.ANIWORLD_TO
                    elif "/serie/stream/" in series_url:
                        slug = series_url.split("/serie/stream/")[-1].rstrip("/")
                        stream_path = "serie/stream"
                        base_url = config.S_TO
                    else:
                        raise ValueError("Invalid series URL format")

                    # Use existing function to get season/episode counts
                    season_counts = get_season_episode_count(slug, base_url)

                    # Build episodes structure
                    episodes_by_season = {}
                    for season_num, episode_count in season_counts.items():
                        if episode_count > 0:
                            episodes_by_season[season_num] = []
                            for ep_num in range(1, episode_count + 1):
                                episodes_by_season[season_num].append(
                                    {
                                        "season": season_num,
                                        "episode": ep_num,
                                        "title": f"Episode {ep_num}",
                                        "url": f"{base_url}/{stream_path}/{slug}/staffel-{season_num}/episode-{ep_num}",
                                    }
                                )

                    # Get movies if this is from aniworld.to (movies only available there)
                    movies = []
                    if base_url == config.ANIWORLD_TO:
                        try:
                            movie_count = get_movie_episode_count(slug)
                            for movie_num in range(1, movie_count + 1):
                                movies.append(
                                    {
                                        "movie": movie_num,
                                        "title": f"Movie {movie_num}",
                                        "url": f"{base_url}/{stream_path}/{slug}/filme/film-{movie_num}",
                                    }
                                )
                        except Exception as e:
                            logging.warning(
                                f"Failed to get movie count for {slug}: {e}"
                            )

                    # Fallback if no seasons found
                    if not episodes_by_season:
                        episodes_by_season[1] = [
                            {
                                "season": 1,
                                "episode": 1,
                                "title": "Episode 1",
                                "url": f"{base_url}/{stream_path}/{slug}/staffel-1/episode-1",
                            }
                        ]

                    return episodes_by_season, movies, slug

                # Use the wrapper function
                try:
                    episodes_by_season, movies, slug = get_episodes_for_series(
                        series_url
                    )
                except ValueError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                except Exception as e:
                    logging.error(f"Failed to get episodes: {e}")
                    return jsonify(
                        {"success": False, "error": "Failed to fetch episodes"}
                    ), 500

                return jsonify(
                    {
                        "success": True,
                        "episodes": episodes_by_season,
                        "movies": movies,
                        "slug": slug,
                    }
                )

            except Exception as err:
                logging.error(f"Episodes fetch error: {err}")
                return jsonify(
                    {"success": False, "error": f"Failed to fetch episodes: {str(err)}"}
                ), 500

        @self.app.route("/api/queue-status")
        @self._require_api_auth
        def api_queue_status():
            """Get download queue status endpoint."""
            try:
                queue_status = self.download_manager.get_queue_status()

                return jsonify({"success": True, "queue": queue_status})
            except Exception as e:
                logging.error(f"Failed to get queue status: {e}")
                return jsonify(
                    {"success": False, "error": "Failed to get queue status"}
                ), 500

        @self.app.route("/api/cancel-download/<int:queue_id>", methods=["POST"])
        @self._require_api_auth
        def api_cancel_download(queue_id):
            """Cancel a download in the queue."""
            try:
                success = self.download_manager.cancel_download(queue_id)
                
                if success:
                    return jsonify({
                        "success": True,
                        "message": "Download cancelled successfully"
                    })
                else:
                    return jsonify({
                        "success": False,
                        "error": "Failed to cancel download or download not found"
                    }), 404
                    
            except Exception as e:
                logging.error(f"Failed to cancel download: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to cancel download: {str(e)}"}
                ), 500

        @self.app.route("/api/popular-new")
        @self._require_api_auth
        def api_popular_new():
            """Get popular and new anime endpoint."""
            try:
                from ..search import fetch_popular_and_new_anime

                anime_data = fetch_popular_and_new_anime()
                return jsonify(
                    {
                        "success": True,
                        "popular": anime_data.get("popular", []),
                        "new": anime_data.get("new", []),
                    }
                )
            except Exception as e:
                logging.error(f"Failed to fetch popular/new anime: {e}")
                return jsonify(
                    {
                        "success": False,
                        "error": f"Failed to fetch popular/new anime: {str(e)}",
                    }
                ), 500

        # Sync Job Management Endpoints
        @self.app.route("/api/sync", methods=["POST"])
        @self._require_api_auth
        def api_create_sync_job():
            """Create a new sync job."""
            if not self.db or not self.sync_manager:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                data = request.get_json()

                anime_title = data.get("anime_title", "").strip()
                series_url = data.get("series_url", "").strip()
                check_interval = data.get("check_interval", 24)
                
                custom_path = data.get("custom_path")
                if custom_path:
                    custom_path = custom_path.strip() or None
                else:
                    custom_path = None
                    
                language = data.get("language", "German Sub")
                provider = data.get("provider", "VOE")

                if not anime_title or not series_url:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Anime title and series URL are required",
                        }
                    ), 400

                # Validate check interval
                try:
                    check_interval_float = float(check_interval)
                    debug_interval = 0.016666
                    valid_intervals = [1, 2, 4, 8, 12, 24]
                    
                    is_valid = False
                    if check_interval_float in valid_intervals:
                        is_valid = True
                    elif abs(check_interval_float - debug_interval) < 0.001:
                        is_valid = True
                        check_interval = debug_interval  # Normalize
                    
                    if not is_valid:
                        return jsonify(
                            {
                                "success": False,
                                "error": f"Invalid check interval. Must be one of: {valid_intervals} or 1 min check",
                            }
                        ), 400
                except (ValueError, TypeError):
                     return jsonify({"success": False, "error": "Invalid interval format"}), 400

                # Get current user
                current_user = None
                if self.auth_enabled and self.db:
                    session_token = request.cookies.get("session_token")
                    current_user = self.db.get_user_by_session(session_token)

                # Create sync job
                sync_job_id = self.db.create_sync_job(
                    anime_title=anime_title,
                    series_url=series_url,
                    check_interval=check_interval,
                    language=language,
                    provider=provider,
                    custom_path=custom_path,
                    created_by=current_user["id"] if current_user else None,
                )

                if sync_job_id:
                    return jsonify(
                        {
                            "success": True,
                            "message": "Sync job created successfully",
                            "sync_job_id": sync_job_id,
                        }
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Failed to create sync job"}
                    ), 500

            except Exception as e:
                logging.error(f"Error creating sync job: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to create sync job: {str(e)}"}
                ), 500

        @self.app.route("/api/sync", methods=["GET"])
        @self._require_api_auth
        def api_get_sync_jobs():
            """Get all sync jobs for current user."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                # Get current user
                current_user = None
                user_id = None
                if self.auth_enabled and self.db:
                    session_token = request.cookies.get("session_token")
                    current_user = self.db.get_user_by_session(session_token)
                    if current_user:
                        user_id = current_user["id"]

                # Get sync jobs
                sync_jobs = self.db.get_sync_jobs(user_id=user_id)

                # Format timestamps for JSON
                for job in sync_jobs:
                    if job.get("created_at"):
                        job["created_at"] = str(job["created_at"])
                    if job.get("last_checked"):
                        job["last_checked"] = str(job["last_checked"])
                    if job.get("last_found_new"):
                        job["last_found_new"] = str(job["last_found_new"])

                return jsonify({"success": True, "sync_jobs": sync_jobs})

            except Exception as e:
                logging.error(f"Error getting sync jobs: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to get sync jobs: {str(e)}"}
                ), 500

        @self.app.route("/api/sync/<int:sync_job_id>", methods=["PUT"])
        @self._require_api_auth
        def api_update_sync_job(sync_job_id):
            """Update a sync job."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                data = request.get_json()

                check_interval = data.get("check_interval")
                custom_path = data.get("custom_path")
                enabled = data.get("enabled")
                language = data.get("language")
                provider = data.get("provider")

                # Validate check interval if provided
                if check_interval is not None:
                    try:
                        check_interval_float = float(check_interval)
                        debug_interval = 0.016666
                        valid_intervals = [1, 2, 4, 8, 12, 24]
                        
                        is_valid = False
                        if check_interval_float in valid_intervals:
                            is_valid = True
                        elif abs(check_interval_float - debug_interval) < 0.001:
                            is_valid = True
                            data["check_interval"] = debug_interval  # Normalize
                            
                        if not is_valid:
                            return jsonify(
                                {
                                    "success": False,
                                    "error": f"Invalid check interval. Must be one of: {valid_intervals} or 1 min check",
                                }
                            ), 400
                    except (ValueError, TypeError):
                        return jsonify({"success": False, "error": "Invalid interval format"}), 400

                # Update sync job
                success = self.db.update_sync_job(
                    sync_job_id=sync_job_id,
                    check_interval=check_interval,
                    custom_path=custom_path,
                    enabled=enabled,
                    language=language,
                    provider=provider,
                )

                if success:
                    return jsonify(
                        {"success": True, "message": "Sync job updated successfully"}
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Failed to update sync job"}
                    ), 500

            except Exception as e:
                logging.error(f"Error updating sync job: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to update sync job: {str(e)}"}
                ), 500

        @self.app.route("/api/sync/<int:sync_job_id>", methods=["DELETE"])
        @self._require_api_auth
        def api_delete_sync_job(sync_job_id):
            """Delete a sync job."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                success = self.db.delete_sync_job(sync_job_id)

                if success:
                    return jsonify(
                        {"success": True, "message": "Sync job deleted successfully"}
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Failed to delete sync job"}
                    ), 500

            except Exception as e:
                logging.error(f"Error deleting sync job: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to delete sync job: {str(e)}"}
                ), 500

        @self.app.route("/api/sync/<int:sync_job_id>/status", methods=["GET"])
        @self._require_api_auth
        def api_get_sync_job_status(sync_job_id):
            """Get detailed status of a sync job."""
            if not self.db:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                sync_job = self.db.get_sync_job(sync_job_id)

                if not sync_job:
                    return jsonify(
                        {"success": False, "error": "Sync job not found"}
                    ), 404

                # Format timestamps
                if sync_job.get("created_at"):
                    sync_job["created_at"] = str(sync_job["created_at"])
                if sync_job.get("last_checked"):
                    sync_job["last_checked"] = str(sync_job["last_checked"])
                if sync_job.get("last_found_new"):
                    sync_job["last_found_new"] = str(sync_job["last_found_new"])

                return jsonify({"success": True, "sync_job": sync_job})

            except Exception as e:
                logging.error(f"Error getting sync job status: {e}")
                return jsonify(
                    {
                        "success": False,
                        "error": f"Failed to get sync job status: {str(e)}",
                    }
                ), 500

        @self.app.route("/api/sync/<int:sync_job_id>/check", methods=["POST"])
        @self._require_api_auth
        def api_force_check_sync_job(sync_job_id):
            """Force an immediate check for a sync job."""
            if not self.sync_manager:
                return jsonify(
                    {"success": False, "error": "Sync functionality not available"}
                ), 400

            try:
                success = self.sync_manager.force_check_job(sync_job_id)

                if success:
                    return jsonify(
                        {
                            "success": True,
                            "message": "Sync job check initiated successfully",
                        }
                    )
                else:
                    return jsonify(
                        {"success": False, "error": "Failed to check sync job"}
                    ), 500

            except Exception as e:
                logging.error(f"Error forcing sync job check: {e}")
                return jsonify(
                    {"success": False, "error": f"Failed to check sync job: {str(e)}"}
                ), 500

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime in human readable format."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours}h {minutes}m {seconds}s"

    def run(self):
        """Run the Flask web application."""
        logging.info("Starting AniWorld Downloader Web Interface...")
        logging.info(f"Server running at http://{self.host}:{self.port}")

        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                use_reloader=False,  # Disable reloader to avoid conflicts
            )
        except KeyboardInterrupt:
            logging.info("Web interface stopped by user")
        except Exception as err:
            logging.error(f"Error running web interface: {err}")
            raise


def create_app(host="127.0.0.1", port=5000, debug=False, arguments=None) -> WebApp:
    """
    Factory function to create web application.

    Args:
        host: Host to bind to
        port: Port to bind to
        debug: Enable debug mode
        arguments: Command line arguments object

    Returns:
        WebApp instance
    """
    return WebApp(host=host, port=port, debug=debug, arguments=arguments)


def start_web_interface(arguments=None, port=5000, debug=False):
    """Start the web interface with configurable settings."""
    # Determine host based on web_expose argument
    host = "0.0.0.0" if getattr(arguments, "web_expose", False) else "127.0.0.1"
    web_app = create_app(host=host, port=port, debug=debug, arguments=arguments)

    # Print startup status
    auth_status = (
        "Authentication ENABLED"
        if getattr(arguments, "enable_web_auth", False)
        else "No Authentication (Local Mode)"
    )
    browser_status = (
        "Browser will open automatically"
        if not getattr(arguments, "no_browser", False)
        else "Browser auto-open disabled"
    )
    expose_status = (
        "ENABLED (0.0.0.0)"
        if getattr(arguments, "web_expose", False)
        else "DISABLED (localhost only)"
    )

    # Get download path
    download_path = str(config.DEFAULT_DOWNLOAD_PATH)
    if (
        arguments
        and hasattr(arguments, "output_dir")
        and arguments.output_dir is not None
    ):
        download_path = str(arguments.output_dir)

    # Show appropriate server address based on host
    server_address = (
        f"http://{host}:{port}" if host == "0.0.0.0" else f"http://localhost:{port}"
    )

    print("\n" + "=" * 69)
    print("🌐 AniWorld Downloader Web Interface")
    print("=" * 69)
    print(f"📍 Server Address:   {server_address}")
    print(f"🔐 Security Mode:    {auth_status}")
    print(f"🌐 External Access:  {expose_status}")
    print(f"📁 Download Path:    {download_path}")
    print(f"🐞 Debug Mode:       {'ENABLED' if debug else 'DISABLED'}")
    print(f"📦 Version:          {config.VERSION}")
    print(f"🌏 Browser:          {browser_status}")
    print("=" * 69)
    print("💡 Access the web interface by opening the URL above in your browser")
    if getattr(arguments, "enable_web_auth", False):
        print("💡 First visit will prompt you to create an admin account")
    print("💡 Press Ctrl+C to stop the server")
    print("=" * 69 + "\n")

    # Open browser automatically unless disabled
    if not getattr(arguments, "no_browser", False):

        def open_browser():
            # Wait a moment for the server to start
            time.sleep(1.5)
            url = f"http://localhost:{port}"
            logging.info(f"Opening browser at {url}")
            try:
                webbrowser.open(url)
            except Exception as e:
                logging.warning(f"Could not open browser automatically: {e}")

        # Start browser opening in a separate thread
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()

    web_app.run()


if __name__ == "__main__":
    start_web_interface()
