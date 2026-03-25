class User {
  const User({
    required this.id,
    required this.email,
    this.name,
    this.roles = const [],
  });

  final String id;
  final String email;
  final String? name;
  final List<String> roles;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as String,
        email: json['email'] as String,
        name: json['name'] as String?,
        roles: (json['roles'] as List<dynamic>?)
                ?.map((e) => e as String)
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        if (name != null) 'name': name,
        'roles': roles,
      };

  bool hasRole(String role) => roles.contains(role);

  bool get isAdmin => hasRole('admin');
}
