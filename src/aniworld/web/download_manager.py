"""
Download Queue Manager for AniWorld Downloader
Handles global download queue processing and status tracking
"""

import threading
import time
import logging
from typing import Optional
from datetime import datetime
from .database import UserDatabase
from .security_utils import validate_custom_path


class DownloadQueueManager:
    """Manages the global download queue processing with in-memory storage"""

    def __init__(self, database: Optional[UserDatabase] = None):
        self.db = database  # Only used for user auth, not download storage
        self.is_processing = False
        self.current_download_id = None
        self.worker_thread = None
        self._stop_event = threading.Event()

        # In-memory download queue storage
        self._next_id = 1
        self._queue_lock = threading.Lock()
        self._active_downloads = {}  # id -> download_job dict
        self._completed_downloads = []  # list of completed download jobs (keep last N)
        self._max_completed_history = 10

    def start_queue_processor(self):
        """Start the background queue processor"""
        if not self.is_processing:
            self.is_processing = True
            self._stop_event.clear()
            self.worker_thread = threading.Thread(
                target=self._process_queue, daemon=True
            )
            self.worker_thread.start()
            logging.info("Download queue processor started")

    def stop_queue_processor(self):
        """Stop the background queue processor"""
        if self.is_processing:
            self.is_processing = False
            self._stop_event.set()
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            logging.info("Download queue processor stopped")

    def is_series_in_progress(self, anime_title: str) -> bool:
        """Check if a download for the given series is already active or queued"""
        with self._queue_lock:
            for download in self._active_downloads.values():
                if download["anime_title"] == anime_title:
                    status = download.get("status")
                    if status in ["queued", "downloading"]:
                        return True
            return False

    def add_download(
        self,
        anime_title: str,
        episode_urls: list,
        language: str,
        provider: str,
        total_episodes: int,
        created_by: int = None,
        custom_path: str = None,
        created_by_username: str = None,
    ) -> int:
        """Add a download to the queue"""
        with self._queue_lock:
            queue_id = self._next_id
            self._next_id += 1

            download_job = {
                "id": queue_id,
                "anime_title": anime_title,
                "episode_urls": episode_urls,
                "language": language,
                "provider": provider,
                "total_episodes": total_episodes,
                "completed_episodes": 0,
                "status": "queued",
                "current_episode": "",
                "progress_percentage": 0.0,
                "current_episode_progress": 0.0,  # Progress within current episode (0-100)
                "error_message": "",
                "created_by": created_by,
                "created_by_username": created_by_username,
                "custom_path": custom_path,  # Custom download path
                "created_at": datetime.now(),
                "started_at": None,
                "completed_at": None,
            }

            self._active_downloads[queue_id] = download_job

        # Start processor if not running
        if not self.is_processing:
            self.start_queue_processor()

        return queue_id

    def get_queue_status(self, user_id: int = None, is_admin: bool = False):
        """
        Get current queue status, optionally filtered by user.
        
        Args:
            user_id: ID of the user requesting status
            is_admin: Whether the user is an admin (sees all)
        """
        with self._queue_lock:
            active_downloads = []
            for download in self._active_downloads.values():
                # Filter by user if not admin and user_id is provided
                if user_id is not None and not is_admin:
                    # If created_by is None (system) or matches user
                    if download["created_by"] is not None and download["created_by"] != user_id:
                        continue

                if download["status"] in ["queued", "downloading"]:
                    # Format for API compatibility
                    active_downloads.append(
                        {
                            "id": download["id"],
                            "anime_title": download["anime_title"],
                            "total_episodes": download["total_episodes"],
                            "completed_episodes": download["completed_episodes"],
                            "status": download["status"],
                            "current_episode": download["current_episode"],
                            "progress_percentage": download["progress_percentage"],
                            "current_episode_progress": download[
                                "current_episode_progress"
                            ],
                            "error_message": download["error_message"],
                            "created_at": download["created_at"].isoformat()
                            if download["created_at"]
                            else None,
                            "created_by": download.get("created_by"),
                            "created_by_username": download.get("created_by_username", "System"),
                        }
                    )

            completed_downloads = []
            # For completed, we iterate slice then filter? No, we likely want last N *for this user*.
            # But traversing the whole list backwards is better.
            
            count = 0
            # Iterate backwards through completed downloads
            for download in reversed(self._completed_downloads):
                if count >= self._max_completed_history:
                    break
                    
                # Filter by user
                if user_id is not None and not is_admin:
                    if download["created_by"] is not None and download["created_by"] != user_id:
                        continue
                
                completed_downloads.append(
                    {
                        "id": download["id"],
                        "anime_title": download["anime_title"],
                        "total_episodes": download["total_episodes"],
                        "completed_episodes": download["completed_episodes"],
                        "status": download["status"],
                        "current_episode": download["current_episode"],
                        "progress_percentage": download["progress_percentage"],
                        "current_episode_progress": download.get(
                            "current_episode_progress", 100.0
                        ),
                        "error_message": download["error_message"],
                        "completed_at": download["completed_at"].isoformat()
                        if download["completed_at"]
                        else None,
                        "created_by": download.get("created_by"),
                        "created_by_username": download.get("created_by_username", "System"),
                    }
                )
                count += 1
            
            return {"active": active_downloads, "completed": completed_downloads}

    def cancel_download(self, queue_id: int, user_id: int = None, is_admin: bool = False) -> bool:
        """
        Cancel a download by queue ID with ownership check.
        
        Args:
            queue_id: The ID of the download to cancel
            user_id: ID of the user requesting cancellation
            is_admin: Whether the user is an admin
            
        Returns:
            True if cancelled successfully, False otherwise (or permission denied)
        """
        with self._queue_lock:
            if queue_id in self._active_downloads:
                download = self._active_downloads[queue_id]
                
                # Check ownership
                if user_id is not None and not is_admin:
                    if download["created_by"] is not None and download["created_by"] != user_id:
                        logging.warning(f"User {user_id} attempted to cancel download {queue_id} owned by {download.get('created_by')}")
                        return False

                # Mark as cancelled
                download["status"] = "cancelled"
                download["error_message"] = "Download cancelled by user"
                download["completed_at"] = datetime.now()
                
                # Move to completed
                self._completed_downloads.append(download)
                del self._active_downloads[queue_id]
                
                logging.info(f"Download {queue_id} cancelled")
                return True
                
        return False

    def _process_queue(self):
        """Background worker that processes the download queue"""
        while self.is_processing and not self._stop_event.is_set():
            try:
                # Get next job
                job = self._get_next_queued_download()

                if job:
                    self.current_download_id = job["id"]
                    self._process_download_job(job)
                    self.current_download_id = None
                else:
                    # No jobs, wait a bit
                    time.sleep(2)

            except Exception as e:
                logging.error(f"Error in queue processor: {e}")
                time.sleep(5)

    def _process_download_job(self, job):
        """Process a single download job"""
        queue_id = job["id"]

        try:
            # Mark as downloading
            self._update_download_status(
                queue_id, "downloading", current_episode="Starting download..."
            )

            # Import necessary modules
            from ..entry import _group_episodes_by_series
            from ..models import Anime
            from pathlib import Path
            from ..action.common import sanitize_filename
            from .. import config
            import os

            # Process episodes
            anime_list = _group_episodes_by_series(job["episode_urls"])

            if not anime_list:
                self._update_download_status(
                    queue_id, "failed", error_message="Failed to process episode URLs"
                )
                return

            # Apply settings to anime objects
            for anime in anime_list:
                anime.language = job["language"]
                anime.provider = job["provider"]
                anime.action = "Download"
                for episode in anime.episode_list:
                    episode._selected_language = job["language"]
                    episode._selected_provider = job["provider"]

            # Calculate actual total episodes after processing URLs
            actual_total_episodes = sum(len(anime.episode_list) for anime in anime_list)

            # Update total episodes count if different from original
            if actual_total_episodes != job["total_episodes"]:
                self._update_download_status(
                    queue_id,
                    "downloading",  # Keep as downloading since we're about to start
                    total_episodes=actual_total_episodes,
                    current_episode=f"Found {actual_total_episodes} valid episode(s) to download",
                )

            # Download logic
            successful_downloads = 0
            failed_downloads = 0
            skipped_downloads = 0  # Track episodes that already exist
            current_episode_index = 0

            # Get download directory - prioritize custom_path from job
            from ..parser import arguments

            download_dir = str(
                getattr(
                    config, "DEFAULT_DOWNLOAD_PATH", os.path.expanduser("~/Downloads")
                )
            )
            if hasattr(arguments, "output_dir") and arguments.output_dir is not None:
                download_dir = str(arguments.output_dir)
            
            # Override with custom path if provided in job
            if job.get("custom_path"):
                try:
                    download_dir = validate_custom_path(str(job["custom_path"]), base_allowed_dir=None)
                    logging.info(f"Using custom download path: {download_dir}")
                except ValueError as e:
                    logging.error(f"Invalid custom path in job {queue_id}: {e}")
                    # Fallback to default download_dir


            for anime in anime_list:
                for episode in anime.episode_list:
                    # Check for global stop
                    if self._stop_event.is_set():
                        break

                    # Check if this specific download was cancelled
                    with self._queue_lock:
                        if queue_id not in self._active_downloads:
                            logging.info(f"Download {queue_id} cancelled during processing")
                            return

                    episode_info = f"{anime.title} - Episode {episode.episode} (Season {episode.season})"

                    # Update progress - reset episode progress to 0 when starting new episode
                    # DON'T update completed_episodes here - it causes the progress bar to jump
                    self._update_download_status(
                        queue_id,
                        "downloading",
                        completed_episodes=None,  # Don't update completed count when starting new episode
                        current_episode=f"Downloading {episode_info}",
                        current_episode_progress=0.0,
                    )

                    try:
                        # Create temp anime with single episode
                        temp_anime = Anime(
                            title=anime.title,
                            slug=anime.slug,
                            site=anime.site,
                            language=anime.language,
                            provider=anime.provider,
                            action=anime.action,
                            episode_list=[episode],
                        )

                        # Create web progress callback for this specific download
                        def web_progress_callback(progress_data):
                            """Handle progress updates from yt-dlp and update web interface"""
                            try:
                                # Check if we should stop during download
                                if self._stop_event.is_set():
                                    # Signal yt-dlp to stop by raising an exception
                                    raise KeyboardInterrupt("Download stopped by user")
                                
                                # Check if this specific download was cancelled
                                with self._queue_lock:
                                    if queue_id not in self._active_downloads:
                                        raise KeyboardInterrupt("Download cancelled by user")

                                # Log the raw progress data for debugging (disabled to reduce spam)
                                # logging.info(f"Progress data received: {progress_data}")

                                if progress_data["status"] == "downloading":
                                    # Try multiple methods to extract progress percentage
                                    percentage = 0.0

                                    # Method 1: _percent_str field
                                    percent_str = progress_data.get("_percent_str")
                                    if percent_str:
                                        try:
                                            percentage = float(
                                                percent_str.replace("%", "")
                                            )
                                        except (ValueError, TypeError):
                                            pass

                                    # Method 2: Calculate from downloaded/total bytes
                                    if percentage == 0.0:
                                        downloaded = progress_data.get(
                                            "downloaded_bytes", 0
                                        )
                                        total = progress_data.get("total_bytes", 0)
                                        if total and total > 0:
                                            percentage = (downloaded / total) * 100

                                    # Method 3: Use fragment info if available
                                    if percentage == 0.0:
                                        fragment_index = progress_data.get(
                                            "fragment_index", 0
                                        )
                                        fragment_count = progress_data.get(
                                            "fragment_count", 0
                                        )
                                        if fragment_count and fragment_count > 0:
                                            percentage = (
                                                fragment_index / fragment_count
                                            ) * 100

                                    # Ensure percentage is valid
                                    percentage = min(100.0, max(0.0, percentage))

                                    # Create status message
                                    speed = progress_data.get("_speed_str", "N/A")
                                    eta = progress_data.get("_eta_str", "N/A")

                                    # Clean ANSI color codes from yt-dlp output
                                    import re

                                    if speed != "N/A":
                                        speed = re.sub(
                                            r"\x1b\[[0-9;]*m", "", str(speed)
                                        ).strip()
                                    if eta != "N/A":
                                        eta = re.sub(
                                            r"\x1b\[[0-9;]*m", "", str(eta)
                                        ).strip()

                                    status_msg = f"Downloading {episode_info} - {percentage:.1f}%"
                                    if speed != "N/A" and speed:
                                        status_msg += f" | Speed: {speed}"
                                    if eta != "N/A" and eta:
                                        status_msg += f" | ETA: {eta}"

                                    # Update episode progress
                                    self.update_episode_progress(
                                        queue_id, percentage, status_msg
                                    )

                                    # Log successful update for debugging (disabled to reduce spam)
                                    # logging.info(f"Updated progress: {percentage:.1f}% for queue {queue_id}")

                                elif progress_data["status"] == "finished":
                                    # Episode completed - don't update progress here
                                    # The progress will be updated correctly after file verification
                                    logging.info(
                                        f"Episode finished for queue {queue_id}"
                                    )

                            except Exception as e:
                                logging.warning(f"Web progress callback error: {e}")

                        # Execute download and capture result
                        try:
                            # Check files before download to better detect success
                            from pathlib import Path

                            # Use the actual configured download directory
                            anime_download_dir = Path(download_dir) / sanitize_filename(
                                anime.title
                            )

                            # Count files before download
                            files_before = 0
                            if anime_download_dir.exists():
                                files_before = len(list(anime_download_dir.glob("*")))

                            # Import and call the new download function with progress callback
                            from ..action.download import download

                            download(temp_anime, web_progress_callback, output_dir=download_dir)

                            # Count files after download
                            files_after = 0
                            if anime_download_dir.exists():
                                files_after = len(list(anime_download_dir.glob("*")))

                            # Check if any new files were created and update progress immediately
                            if files_after > files_before:
                                successful_downloads += 1
                                logging.info(f"Downloaded: {episode_info}")

                                # Update completed episodes count ONLY after successful download
                                self._update_download_status(
                                    queue_id,
                                    "downloading",
                                    completed_episodes=successful_downloads,  # Update completed count after successful download
                                    current_episode=f"Completed {episode_info}",
                                    current_episode_progress=100.0,
                                )
                            else:
                                # No new files created - episode was skipped (already exists)
                                skipped_downloads += 1
                                logging.info(
                                    f"Skipped (already exists): {episode_info}"
                                )

                        except KeyboardInterrupt:
                            # Handle cancellation/interruption
                            logging.info(f"Download cancelled: {episode_info}")
                            with self._queue_lock:
                                # Ensure it's marked as cancelled if not already (it should be)
                                if queue_id in self._active_downloads:
                                    # This happens if we stopped due to server shutdown, not user cancel
                                    pass
                            return  # Stop processing this job

                        except Exception as download_error:
                            # If an exception was raised during download, it failed
                            failed_downloads += 1
                            logging.warning(
                                f"Failed to download: {episode_info} - Error: {download_error}"
                            )

                    except Exception as e:
                        failed_downloads += 1
                        logging.error(f"Error downloading {episode_info}: {e}")

                    current_episode_index += 1

            # Final status update
            total_attempted = successful_downloads + failed_downloads + skipped_downloads
            
            if successful_downloads == 0 and skipped_downloads > 0 and failed_downloads == 0:
                # All episodes were skipped (already downloaded)
                status = "completed"
                error_msg = f"All {skipped_downloads} episode(s) already downloaded."
            elif successful_downloads == 0 and failed_downloads > 0:
                # No successful downloads and some failures
                status = "failed"
                error_msg = f"Download failed: No episodes downloaded out of {failed_downloads} attempted."
            elif failed_downloads > 0:
                # Partial success
                status = "completed"
                error_msg = f"Partially completed: {successful_downloads}/{total_attempted} episodes downloaded ({skipped_downloads} skipped, {failed_downloads} failed)."
            else:
                # All successful (or all skipped)
                status = "completed"
                if skipped_downloads > 0:
                    error_msg = f"Successfully downloaded {successful_downloads} episode(s), {skipped_downloads} already existed."
                else:
                    error_msg = f"Successfully downloaded {successful_downloads} episode(s)."

            self._update_download_status(
                queue_id,
                status,
                completed_episodes=successful_downloads,
                current_episode=error_msg,
                error_message=error_msg if status == "failed" else None,
            )

        except Exception as e:
            logging.error(f"Download job {queue_id} failed: {e}")
            self._update_download_status(
                queue_id, "failed", error_message=f"Download failed: {str(e)}"
            )

    def _get_next_queued_download(self):
        """Get the next download job in the queue"""
        with self._queue_lock:
            for download in self._active_downloads.values():
                if download["status"] == "queued":
                    return download
            return None

    def update_episode_progress(
        self, queue_id: int, episode_progress: float, current_episode_desc: str = None
    ):
        """Update the progress within the current episode"""
        with self._queue_lock:
            if queue_id not in self._active_downloads:
                return False

            download = self._active_downloads[queue_id]
            download["current_episode_progress"] = min(
                100.0, max(0.0, episode_progress)
            )

            if current_episode_desc:
                download["current_episode"] = current_episode_desc

            # Calculate overall progress: completed episodes + current episode progress
            completed = download["completed_episodes"]
            total = download["total_episodes"]
            if total > 0:
                current_episode_contribution = (
                    (episode_progress / 100.0) if episode_progress >= 0 else 0
                )
                new_progress = (completed + current_episode_contribution) / total * 100
                download["progress_percentage"] = new_progress

            return True

    def _update_download_status(
        self,
        queue_id: int,
        status: str,
        completed_episodes: int = None,
        current_episode: str = None,
        error_message: str = None,
        total_episodes: int = None,
        current_episode_progress: float = None,
    ):
        """Update the status of a download job"""
        with self._queue_lock:
            if queue_id not in self._active_downloads:
                return False

            download = self._active_downloads[queue_id]
            download["status"] = status

            if completed_episodes is not None:
                download["completed_episodes"] = completed_episodes
                # Calculate progress percentage - only use current episode progress if status is downloading and we haven't completed this episode yet
                total = download["total_episodes"]
                current_ep_progress = download.get("current_episode_progress", 0.0)

                if total > 0:
                    # For completed episodes, don't add extra current episode contribution
                    # since the episode is already counted as completed
                    if status == "downloading" and current_ep_progress < 100.0:
                        # Episode is in progress, add partial progress
                        current_episode_contribution = (
                            (current_ep_progress / 100.0)
                            if current_ep_progress >= 0
                            else 0
                        )
                        new_progress = (
                            (completed_episodes + current_episode_contribution)
                            / total
                            * 100
                        )
                    else:
                        # Episode is completed or we're not actively downloading, use completed count only
                        new_progress = completed_episodes / total * 100

                    download["progress_percentage"] = new_progress
                else:
                    download["progress_percentage"] = 0

            if current_episode is not None:
                download["current_episode"] = current_episode

            if current_episode_progress is not None:
                download["current_episode_progress"] = min(
                    100.0, max(0.0, current_episode_progress)
                )

                # If we're updating episode progress but not completed_episodes,
                # recalculate overall progress with current values
                if completed_episodes is None:
                    total = download["total_episodes"]
                    current_completed = download["completed_episodes"]
                    if total > 0:
                        # Only add current episode contribution if actively downloading and episode not yet completed
                        if status == "downloading" and current_episode_progress < 100.0:
                            current_episode_contribution = (
                                (current_episode_progress / 100.0)
                                if current_episode_progress >= 0
                                else 0
                            )
                            new_progress = (
                                (current_completed + current_episode_contribution)
                                / total
                                * 100
                            )
                        else:
                            # Use completed count only
                            new_progress = current_completed / total * 100

                        download["progress_percentage"] = new_progress

            if error_message is not None:
                download["error_message"] = error_message

            if total_episodes is not None:
                download["total_episodes"] = total_episodes

            # Update timestamps based on status
            if status == "downloading" and download["started_at"] is None:
                download["started_at"] = datetime.now()
            elif status in ["completed", "failed"]:
                download["completed_at"] = datetime.now()
                # Set final progress for completed downloads
                if status == "completed":
                    download["current_episode_progress"] = 100.0
                    download["progress_percentage"] = 100.0

                # Move to completed list and remove from active
                self._completed_downloads.append(download.copy())
                # Keep only recent completed downloads
                if len(self._completed_downloads) > self._max_completed_history:
                    self._completed_downloads = self._completed_downloads[
                        -self._max_completed_history :
                    ]

                # Remove from active downloads
                del self._active_downloads[queue_id]

            return True


# Global instance
_download_manager = None


def get_download_manager(
    database: Optional[UserDatabase] = None,
) -> DownloadQueueManager:
    """Get or create the global download manager instance"""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadQueueManager(database)
    return _download_manager
