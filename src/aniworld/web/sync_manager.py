"""
Sync Manager for AniWorld Downloader
Handles automatic checking and downloading of new episodes
"""

import threading
import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from .database import UserDatabase
from .download_manager import DownloadQueueManager


class SyncManager:
    """Manages automatic sync jobs for checking and downloading new episodes"""

    def __init__(
        self, database: UserDatabase, download_manager: DownloadQueueManager
    ):
        self.db = database
        self.download_manager = download_manager
        self.is_running = False
        self.worker_thread = None
        self._stop_event = threading.Event()
        self._check_lock = threading.Lock()

    def start(self):
        """Start the background sync checker"""
        if not self.is_running:
            self.is_running = True
            self._stop_event.clear()
            self.worker_thread = threading.Thread(target=self._sync_loop, daemon=True)
            self.worker_thread.start()
            logging.info("Sync manager started")

    def stop(self):
        """Stop the background sync checker"""
        if self.is_running:
            self.is_running = False
            self._stop_event.set()
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            logging.info("Sync manager stopped")

    def _sync_loop(self):
        """Background loop that checks sync jobs periodically"""
        while self.is_running and not self._stop_event.is_set():
            try:
                # Check every minute for jobs that need checking
                self._check_due_jobs()
                time.sleep(60)  # Check every minute

            except Exception as e:
                logging.error(f"Error in sync loop: {e}")
                time.sleep(60)

    def _check_due_jobs(self):
        """Check for sync jobs that are due for checking"""
        try:
            # Get all enabled sync jobs
            sync_jobs = self.db.get_sync_jobs(enabled_only=True)

            for job in sync_jobs:
                if self._is_job_due(job):
                    logging.info(
                        f"Checking sync job: {job['anime_title']} (ID: {job['id']})"
                    )
                    self._check_and_download_new_episodes(job)

        except Exception as e:
            logging.error(f"Error checking due jobs: {e}")

    def _is_job_due(self, job: dict) -> bool:
        """
        Check if a sync job is due for checking.

        Args:
            job: Sync job dictionary

        Returns:
            True if job is due for checking, False otherwise
        """
        if not job.get("last_checked"):
            # Never checked, so it's due
            return True

        try:
            # Parse last_checked timestamp
            last_checked = datetime.fromisoformat(
                job["last_checked"].replace("Z", "+00:00")
            )
            check_interval_hours = job["check_interval"]
            next_check = last_checked + timedelta(hours=check_interval_hours)

            return datetime.now() >= next_check

        except Exception as e:
            logging.error(f"Error checking if job is due: {e}")
            return True  # If error, assume it's due

    def _check_and_download_new_episodes(self, job: dict):
        """
        Check for new or missing episodes and download if found.
        """
        with self._check_lock:
            # Check if download is already active to prevent duplicates
            if self.download_manager.is_series_in_progress(job["anime_title"]):
                logging.debug(f"Skipping sync for {job['anime_title']}: Download already in progress")
                return

            try:
                # Imports for path and filename handling
                from pathlib import Path
                import re
                from .. import config
                from ..action.common import sanitize_filename

                # Get all episode URLs with S/E mapping
                # Returns list of tuples: (season, episode, url, is_movie)
                all_episodes = self._get_all_episodes(job["series_url"])
                
                if not all_episodes:
                    logging.warning(f"No episodes found for {job['anime_title']}")
                    return

                # Determine local directory
                base_path = job.get("custom_path")
                if not base_path:
                    # Fallback to default download dir
                    if hasattr(config, 'DOWNLOAD_DIR'):
                        base_path = config.DOWNLOAD_DIR
                    else:
                        base_path = "Downloads"

                anime_dir = Path(base_path) / sanitize_filename(job["anime_title"])
                
                # Scan local files
                local_episodes = set() # Set of (season, episode, is_movie)
                
                if anime_dir.exists():
                    for file_path in anime_dir.rglob("*"):
                        if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.mkv', '.avi']:
                            name = file_path.name
                            
                            # Check for Season/Episode pattern (S01E01)
                            se_match = re.search(r"[Ss](\d+)[Ee](\d+)", name)
                            if se_match:
                                local_episodes.add((int(se_match.group(1)), int(se_match.group(2)), False))
                                continue
                                
                            # Check for Movie pattern (Film 1, Movie 1)
                            movie_match = re.search(r"(?:Film|Movie)[._\s-]*(\d+)", name, re.IGNORECASE)
                            if movie_match:
                                local_episodes.add((0, int(movie_match.group(1)), True))
                                continue

                # Identifiy missing episodes
                missing_urls = []
                current_ep_count = len(all_episodes)
                
                for season, episode, url, is_movie in all_episodes:
                    key = (season, episode, is_movie)
                    # For movies, we use season 0 within the set
                    if is_movie:
                         key = (0, episode, True)
                         
                    if key not in local_episodes:
                        missing_urls.append(url)

                if missing_urls:
                    logging.info(
                        f"Found {len(missing_urls)} missing/new episode(s) for {job['anime_title']}"
                    )
                    
                    # Add to download queue
                    self.download_manager.add_download(
                        anime_title=job["anime_title"],
                        episode_urls=missing_urls,
                        language=job["language"],
                        provider=job["provider"],
                        total_episodes=len(missing_urls),
                        created_by=job.get("created_by"),
                        custom_path=job.get("custom_path")
                    )
                else:
                    logging.debug(f"All {current_ep_count} episodes exist for {job['anime_title']}")

                # Update DB status
                self.db.update_sync_job_check_status(
                    job["id"], 
                    last_episode_count=current_ep_count,
                    found_new=bool(missing_urls)
                )

            except Exception as e:
                logging.error(f"Error checking and downloading episodes for {job['anime_title']}: {e}")
                # Update timestamp anyway to avoid loop
                self.db.update_sync_job_check_status(
                     job["id"], last_episode_count=job.get("last_episode_count", 0)
                )

    def _get_episode_count(self, series_url: str) -> Optional[int]:
        """
        Get the total episode count for a series.

        Args:
            series_url: URL to the series page

        Returns:
            Total episode count, or None if failed
        """
        try:
            from ..common import get_season_episode_count, get_movie_episode_count
            from ..entry import _detect_site_from_url
            from .. import config

            # Extract slug and site
            _site = _detect_site_from_url(series_url)

            if "/anime/stream/" in series_url:
                slug = series_url.split("/anime/stream/")[-1].rstrip("/")
                base_url = config.ANIWORLD_TO
            elif "/serie/stream/" in series_url:
                slug = series_url.split("/serie/stream/")[-1].rstrip("/")
                base_url = config.S_TO
            else:
                logging.error(f"Invalid series URL format: {series_url}")
                return None

            # Get season/episode counts
            season_counts = get_season_episode_count(slug, base_url)
            total_episodes = sum(season_counts.values())

            # Add movies if from aniworld.to
            if base_url == config.ANIWORLD_TO:
                try:
                    movie_count = get_movie_episode_count(slug)
                    total_episodes += movie_count
                except Exception:
                    pass  # Movies are optional

            return total_episodes

        except Exception as e:
            logging.error(f"Error getting episode count: {e}")
            return None

    def _get_all_episodes(self, series_url: str) -> list:
        """
        Get all episode URLs with metadata.
        Returns: List of (season, episode, url, is_movie)
        """
        try:
            from ..common import get_season_episode_count, get_movie_episode_count
            from .. import config

            # Extract slug and site
            if "/anime/stream/" in series_url:
                slug = series_url.split("/anime/stream/")[-1].rstrip("/")
                stream_path = "anime/stream"
                base_url = config.ANIWORLD_TO
            elif "/serie/stream/" in series_url:
                slug = series_url.split("/serie/stream/")[-1].rstrip("/")
                stream_path = "serie/stream"
                base_url = config.S_TO
            else:
                return []

            results = []

            # Get seasons
            season_counts = get_season_episode_count(slug, base_url)
            for season_num, episode_count in season_counts.items():
                if episode_count > 0:
                    for ep_num in range(1, episode_count + 1):
                        url = f"{base_url}/{stream_path}/{slug}/staffel-{season_num}/episode-{ep_num}"
                        results.append((season_num, ep_num, url, False))

            # Add movies if from aniworld.to
            if base_url == config.ANIWORLD_TO:
                try:
                    movie_count = get_movie_episode_count(slug)
                    for movie_num in range(1, movie_count + 1):
                        url = f"{base_url}/{stream_path}/{slug}/filme/film-{movie_num}"
                        results.append((0, movie_num, url, True)) # Season 0 for movies
                except Exception:
                    pass

            return results

        except Exception as e:
            logging.error(f"Error getting episode URLs: {e}")
            return []

    def force_check_job(self, sync_job_id: int) -> bool:
        """
        Force an immediate check for a specific sync job.

        Args:
            sync_job_id: Sync job ID to check

        Returns:
            True if check was successful, False otherwise
        """
        try:
            job = self.db.get_sync_job(sync_job_id)
            if not job:
                logging.error(f"Sync job {sync_job_id} not found")
                return False

            if not job.get("enabled"):
                logging.warning(f"Sync job {sync_job_id} is disabled")
                return False

            self._check_and_download_new_episodes(job)
            return True

        except Exception as e:
            logging.error(f"Error force checking sync job {sync_job_id}: {e}")
            return False


# Global instance
_sync_manager = None


def get_sync_manager(
    database: UserDatabase, download_manager: DownloadQueueManager
) -> SyncManager:
    """Get or create the global sync manager instance"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(database, download_manager)
    return _sync_manager
