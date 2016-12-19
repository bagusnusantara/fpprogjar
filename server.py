from PodSixNet.Channel import Channel
from PodSixNet.Server import Server
from time import sleep
from weakref import WeakKeyDictionary
from ConfigParser import SafeConfigParser


class ServerChannel(Channel):

    def __init__(self, *args, **kwargs):
        Channel.__init__(self, *args, **kwargs)
        self.assign_player_counter = 0

    def Close(self):
        print "close"
        self._server.DeleteClient(self)

    def PassOn(self, data):
        # print "PassOn", data
        if data["action"] == "broadcast_request":
            self._server.BroadcastGameStatus(self)

        elif data["action"] == "quit":
            self.Close()

        elif data["action"] == "attack":
            self._server.UpdateBoard(self, data)

        elif data["action"] == "ready":
            print data
            self._server.InitBoard(self, data)

    # Get data here
    def Network(self, data):
        self.PassOn(data)


class GameServer(Server):

    channelClass = ServerChannel

    def __init__(self, *args, **kwargs):
        Server.__init__(self, *args, **kwargs)
        self.clients = WeakKeyDictionary()
        # [[room_full_flag, ready_state, player_who_get_first_turn],
        # [board1, board2, player_owns_board1, player_owns_board2], status, player1, player2]
        # room_full_flag=1 means room is full
        self.client_pairs = []
        print 'Server launched'

    def Connected(self, channel, addr):
        print "new connection: ", channel
        print "New Player" + str(channel.addr)
        self.clients[channel] = True
        self.Matchmaking(channel)
        temp_data = {"action": "matchmaking"}
        channel.Send(temp_data)
        # print self.client_pairs

    # Client and room deletion management
    def DeleteClient(self, channel):
        print "Deleting", channel
        still_checking = 1

        for i in range(len(self.client_pairs)):
            for j in range(len(self.client_pairs[i])):
                if self.client_pairs[i][j] == channel:
                    # Replace board status
                    self.client_pairs[i][2] = "opponent_disconnected"
                    # If room is on full state, make sure there's another client there
                    # Broadcast to other player
                    if self.client_pairs[i][0][0] == 1 and len(self.client_pairs[i]) == 5:
                        # If index = 2, then index = 3 is the other client
                        if j == 3:
                            self.BroadcastGameStatus(self.client_pairs[i][4])
                        # If index = 3, then index = 2 is the other client
                        elif j == 4:
                            self.BroadcastGameStatus(self.client_pairs[i][3])
                        # Delete client from room
                        del self.client_pairs[i][j]
                        # If room is on full state and one client is already out
                    elif self.client_pairs[i][0][0] == 1 and len(self.client_pairs[i]) == 4:
                        # Delete this room
                        print "Deleting room"
                        del self.client_pairs[i]
                    # If room is not full and this client wants to exit
                    elif self.client_pairs[i][0][0] == 0:
                        # Delete this room
                        print "Deleting room"
                        del self.client_pairs[i]

                    still_checking = 0
                    break

            if still_checking == 0:
                break
        # Delete this client from client channel dictionary
        del self.clients[channel]

    # Anonymous game session creator
    def Matchmaking(self, channel):
        board = [[0 for x in range(10)] for y in range(10)]
        status = "find_match"
        room_full_flag = 0
        ready_state = 0
        # If no room exists
        if len(self.client_pairs) == 0:
            self.client_pairs.append([[room_full_flag, ready_state, None], [board, board], status, channel])

        # if at least a room exists
        else:
            # Assume this client has no room.
            got_no_room = 1
            # Check every pair in client_pairs
            for pair in self.client_pairs:
                # If room full flag is 0 means it's not full, join client to this room
                if pair[0][0] == 0:
                    pair.append(channel)
                    # This room is full now
                    pair[0][0] = 1
                    # Because it's full, both players are entering the deploy_phase
                    pair[2] = "deploy_phase"
                    # Congratulations! This client gets a room
                    got_no_room = 0
                    break

            # If all rooms already full, make a new one
            if got_no_room == 1:
                self.client_pairs.append([[room_full_flag, ready_state, None], [board, board], status, channel])

        # print self.client_pairs

    # Send message to itself, other client, or both clients based on flag
    def SendToOther(self, channel, data, flag=1):
        # print "SendToOther", data
        sender = None
        receiver = None
        for pair in self.client_pairs:
            # If there are two users in room
            if pair[0][0] == 1 and len(pair) == 5:
                if pair[3] == channel:
                    sender = pair[3]
                    receiver = pair[4]
                    break
                elif pair[4] == channel:
                    sender = pair[4]
                    receiver = pair[3]
                    break
            # If room is already on full state but the other party quit
            elif pair[0][0] == 1 and len(pair) == 4:
                receiver = pair[3]
                flag = 1

        # Send to other player in room
        if flag == 1:
            del data["player_1"]
            del data["player_2"]
            receiver.Send(data)
        # Send to both player in room
        elif flag == 2:
            temp_player_1 = data["player_1"]
            temp_player_2 = data["player_2"]
            del data["player_1"]
            del data["player_2"]

            if temp_player_1 == receiver:
                data["order"] = "player_1"
                receiver.Send(data)

            elif temp_player_1 == sender:
                data["order"] = "player_1"
                sender.Send(data)

            if temp_player_2 == receiver:
                data["order"] = "player_2"
                receiver.Send(data)

            elif temp_player_2 == sender:
                data["order"] = "player_2"
                sender.Send(data)

            if temp_player_1 is None or temp_player_2 is None:
                del data["order"]
                receiver.Send(data)
                sender.Send(data)

        # Send to who made request
        elif flag == 3:
            del data["player_1"]
            del data["player_2"]
            channel.Send(data)

    # Broadcast game status and determine player order
    def BroadcastGameStatus(self, channel):
        player_1 = None
        player_2 = None
        board_counter = self.WinningCheck(channel)
        for pair in self.client_pairs:
            for index in range(len(pair)):
                if pair[index] == channel:
                    temp_data = {"action": "broadcast", "status": pair[2], "board_state": pair[1], "board_counter": board_counter, "order": None, "player_1": None, "player_2": None}
                    # If only one player exists, broadcast to itself alone
                    if pair[0][0] == 0:
                        # Room: One player, probably still matchmaking
                        self.SendToOther(channel, temp_data, flag=3)
                    # If other player exists, broadcast to both players in room
                    elif pair[0][0] == 1:
                        # To set player order
                        if len(pair) == 5:
                            if pair[0][2] == channel:
                                if index == 3:
                                    player_2 = pair[3]
                                    player_1 = pair[4]
                                elif index == 4:
                                    player_2 = pair[4]
                                    player_1 = pair[3]
                                temp_data = {"action": "broadcast", "status": pair[2], "board_state": pair[1], "board_counter": board_counter, "player_1": player_1, "player_2": player_2}

                        # Room: Two players, probably in a game session
                        # Let's test it by using flag = 2
                        self.SendToOther(channel, temp_data, flag=2)

    def InitBoard(self, channel, data):
        still_checking = 1
        board_number = None
        for i in range(len(self.client_pairs)):
            for j in range(len(self.client_pairs[i])):
                if self.client_pairs[i][j] == channel:
                    # Update player ready_state
                    self.client_pairs[i][0][1] += 1
                    if j == 3:
                        board_number = 0
                    elif j == 4:
                        board_number = 1

                    # Update board state to deploy_phase result
                    self.client_pairs[i][1][board_number] = data["my_board"]
                    # To mark which board is player's board
                    # self.client_pairs[i][1].append(j)

                    # Send ready_state to players if both are ready
                    if self.client_pairs[i][0][1] == 2:
                        # Change game status to player_1 means first one who submit the board will take the first turn
                        self.client_pairs[i][2] = "player_1"
                        self.client_pairs[i][0][2] = channel

                    still_checking = 0
                    break

            if still_checking == 0:
                break

    def UpdateBoard(self, channel, data):
        print "Update board"
        still_checking = 1
        board_number = None
        for i in range(len(self.client_pairs)):
            for j in range(len(self.client_pairs[i])):
                if self.client_pairs[i][j] == channel:
                    if j == 3:
                        board_number = 1
                    elif j == 4:
                        board_number = 0
                    # Extract row and col data
                    row = data["row"]
                    col = data["col"] - 10  # Normalize
                    # Update board state to attack result
                    # If part of ship is there, give it hit
                    print "board: ", board_number, "row: ", row, "col: ", col
                    if self.client_pairs[i][1][board_number][row][col] == 1:
                        self.client_pairs[i][1][board_number][row][col] = -1
                        # Bonus move
                        if j == 3:
                            self.client_pairs[i][2] = "player_1"
                        elif j == 4:
                            self.client_pairs[i][2] = "player_2"

                    elif self.client_pairs[i][1][board_number][row][col] == 0:
                        self.client_pairs[i][1][board_number][row][col] = -2
                        # Update game status
                        if self.client_pairs[i][2] == "player_1":
                            self.client_pairs[i][2] = "player_2"
                        elif self.client_pairs[i][2] == "player_2":
                            self.client_pairs[i][2] = "player_1"

                    print self.client_pairs[i][2]
                    still_checking = 0

                    print self.client_pairs[i][1][board_number]
                    break

            if still_checking == 0:
                break

    def WinningCheck(self, channel):
        board_1_counter = None
        board_2_counter = None
        still_checking = 1
        for room in self.client_pairs:
            for index in range(len(room)):
                if room[index] == channel:
                    # if len(room[1]) == 4:
                    board_1_counter = 0
                    board_2_counter = 0
                    for i in range(10):
                        for j in range(10):
                            if room[1][0][i][j] == 1:
                                board_1_counter += 1

                    for i in range(10):
                        for j in range(10):
                            if room[1][1][i][j] == 1:
                                board_2_counter += 1

                    still_checking = 0
                    break

            if still_checking == 0:
                break

        board_counter = [board_1_counter, board_2_counter]
        return board_counter

    def print_client_pairs(self):
        for i in range(len(self.client_pairs)):
            print "--------------"
            print i
            for j in range(len(self.client_pairs[i])):
                print self.client_pairs[i][j]
            print "--------------"

    # Main loop
    def Loop(self):
        while True:
            self.Pump()
            self.print_client_pairs()
            # sleep(0.0001)

if __name__ == "__main__":
    # Reading configuration file for server settings
    parser = SafeConfigParser()
    parser.read('network.conf')

    # Define port and server address
    server_address = parser.get('game_server', 'server_address')
    port = parser.get('game_server', 'port')
    port = int(port)

    battleship_server = GameServer(localaddr=(server_address, port))
    battleship_server.Loop()
