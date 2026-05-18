import io from 'socket.io-client';
import useAuthStore from '../store/authStore';
import useNotificationStore from '../store/notificationStore';
import useProjectStore from '../store/projectStore';
import useTaskStore from '../store/taskStore';
import toast from 'react-hot-toast';

let socket = null;

export const initSocket = () => {
    const { user } = useAuthStore.getState();
    if (!user || socket?.connected) return;

    socket = io('http://localhost:5000', {
        withCredentials: true,
        transports: ['websocket']
    });

    socket.on('connect', () => {
        console.log('🔌 Socket.IO connected');
        // Request sync of recent events
        socket.emit('sync_required', {});
    });

    socket.on('connected', (data) => {
        console.log('Server ack:', data);
    });

    socket.on('notification', (data) => {
        // Show toast
        toast(data.message || `${data.title}`, {
            icon: '🔔',
            duration: 5000
        });
        // Add to in-app notification store
        useNotificationStore.getState().addNotification(data);
        // Update unread badge count
        const { setUnreadCount } = useAuthStore.getState();
        setUnreadCount((prev) => prev + 1);
    });

    socket.on('dashboard_update', ({ entity }) => {
        // Trigger refetch of specific data based on entity
        if (entity === 'projects') {
            useProjectStore.getState().refetchProjects?.();
        } else if (entity === 'tasks') {
            useTaskStore.getState().refetchTasks?.();
        } else if (entity === 'proposals') {
            // if you have a proposal store
            window.dispatchEvent(new CustomEvent('refetch-proposals'));
        }
    });

    socket.on('project_update', ({ project_id, status }) => {
        // Update project status in local store without full refetch
        useProjectStore.getState().updateProjectStatus?.(project_id, status);
        toast.success(`Project #${project_id} status changed to ${status}`);
    });

    socket.on('payment_received', ({ amount, type }) => {
        toast.success(`💰 Payment of $${amount} received (${type})`);
        // Trigger balance/transaction refresh
        window.dispatchEvent(new CustomEvent('refresh-finances'));
    });

    socket.on('phase_completed', ({ phase_name, project_id }) => {
        toast.success(`Phase "${phase_name}" completed!`);
        // Refresh project details if currently viewing
        window.dispatchEvent(new CustomEvent('refresh-project', { detail: { project_id } }));
    });

    socket.on('sync_data', (data) => {
        // Populate missed notifications
        if (data.notifications?.length) {
            data.notifications.forEach(notif => {
                useNotificationStore.getState().addNotification(notif);
            });
            const { setUnreadCount } = useAuthStore.getState();
            setUnreadCount(data.notifications.filter(n => !n.is_read).length);
        }
    });

    socket.on('disconnect', () => {
        console.log('🔌 Socket.IO disconnected');
    });
};

export const disconnectSocket = () => {
    if (socket) {
        socket.disconnect();
        socket = null;
    }
};

// Optional: function to join project rooms dynamically
export const joinProjectRoom = (projectId) => {
    if (socket) {
        socket.emit('join_project', { project_id: projectId });
    }
};